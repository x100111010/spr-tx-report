import requests
import csv
import datetime

API_BASE = "https://api.spectre-network.org"
PAGE_SIZE = 500
SOMPIS_TO_SPR = 100000000

ADDRESSES = [
    "spectre:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "spectre:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    "spectre:ccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
]  # define addresses here


def format_date(timestamp):
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        timestamp = timestamp / 1000
        return datetime.datetime.utcfromtimestamp(timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    else:
        return "Invalid Timestamp"


def sompi_to_spr(amount):
    return amount / SOMPIS_TO_SPR


def fetch_transactions(addresses):
    print("Starting transaction fetch...")
    tx_cache = {}
    txs = find_all_transactions(addresses, tx_cache)

    additional_tx_to_search = []

    for tx in txs:
        inputs = tx.get("inputs", []) or []
        for i in inputs:
            if i["previous_outpoint_hash"] not in tx_cache:
                additional_tx_to_search.append(i["previous_outpoint_hash"])

    print(f"Found {len(additional_tx_to_search)} additional transactions to search.")

    for page in range(0, len(additional_tx_to_search), PAGE_SIZE):
        batch = additional_tx_to_search[page : page + PAGE_SIZE]
        print(f"Fetching additional transactions batch {page + 1}...")
        get_additional_transactions(batch, tx_cache)

    processed_txs = []
    for tx in txs:
        print(f"Processing transaction {tx['transaction_id']}")
        outpointed_inputs = []
        inputs = tx.get("inputs", []) or []
        for inp in inputs:
            prev_hash = inp["previous_outpoint_hash"]
            if prev_hash in tx_cache:
                output = next(
                    (
                        o
                        for o in tx_cache[prev_hash]["outputs"]
                        if o["index"] == inp["previous_outpoint_index"]
                    ),
                    None,
                )
                outpointed_inputs.append(output)
            else:
                outpointed_inputs.append({"transaction_id": prev_hash})

        send_amount = sum(
            outp.get("amount", outp.get("previous_outpoint_amount", 0))
            for outp in outpointed_inputs
            if outp
        )
        receive_amount = sum(outp["amount"] for outp in tx["outputs"] if outp)
        fee_amount = sum(
            outp.get("amount", outp.get("previous_outpoint_amount", 0))
            for outp in outpointed_inputs
            if outp
        ) - sum(outp["amount"] for outp in tx["outputs"] if outp)

        tx_result = {
            "timestamp": format_date(tx.get("block_time")),
            "txHash": tx["transaction_id"],
            "sendAmount": sompi_to_spr(send_amount - receive_amount - fee_amount)
            if send_amount > receive_amount
            else 0,
            "receiveAmount": sompi_to_spr(receive_amount - send_amount)
            if receive_amount > send_amount
            else 0,
            "feeAmount": sompi_to_spr(fee_amount) if fee_amount > 0 else 0,
        }
        processed_txs.append(tx_result)

    print("Transaction fetch completed.")
    return processed_txs


def find_all_transactions(addresses, tx_cache):
    txs = []
    for address in addresses:
        print(f"Fetching transactions for: {address}")
        address_txs = get_address_transactions(address, tx_cache)
        txs.extend(address_txs)
    txs.sort(key=lambda x: x["block_time"])
    print(f"Total transactions found: {len(txs)}")
    return txs


def get_additional_transactions(txs, tx_cache):
    print(f"Fetching additional {len(txs)} transactions...")
    response = requests.post(
        f"{API_BASE}/transactions/search", json={"transactionIds": txs}
    )
    response.raise_for_status()
    transactions_response = response.json()
    for tx in transactions_response:
        tx_cache[tx["transaction_id"]] = tx
    print("Additional transactions fetched successfully.")


def get_address_transactions(address, tx_cache):
    txs = []
    print(f"Fetching transaction count for address: {address}")
    response = requests.get(f"{API_BASE}/addresses/{address}/transactions-count")
    response.raise_for_status()
    tx_count = response.json().get("total", 0)

    print(f"Address {address} has {tx_count} transactions.")

    for offset in range(0, tx_count, PAGE_SIZE):
        print(f"Fetching transactions from {address}, offset {offset}...")
        response = requests.get(
            f"{API_BASE}/addresses/{address}/full-transactions",
            params={"offset": offset, "limit": PAGE_SIZE},
        )
        response.raise_for_status()
        page_txs = response.json()

        for tx in page_txs:
            tx_cache[tx["transaction_id"]] = tx
            if tx.get("is_accepted", False):
                txs.append(tx)

    print(f"Fetched {len(txs)} transactions for {address}.")
    return txs


def save_to_csv(transactions, filename="transactions.csv"):
    keys = transactions[0].keys() if transactions else []
    with open(filename, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        writer.writerows(transactions)
    print(f"Transactions saved to {filename}")


if __name__ == "__main__":
    print("Started.")
    transactions = fetch_transactions(ADDRESSES)
    save_to_csv(transactions)
    print("Completed.")
