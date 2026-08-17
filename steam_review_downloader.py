import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime
import aiohttp

# Unix Timestamps for 2025 (UTC)
START_2025 = 1735689600  # Jan 1, 2025
END_2025 = 1767225599    # Dec 31, 2025

REVIEW_FOLDER = 'data/2025_reviews'
os.makedirs(REVIEW_FOLDER, exist_ok=True)

# Limit concurrent games being processed at the same time to prevent 429 errors
MAX_CONCURRENT_GAMES = 3
semaphore = asyncio.Semaphore(MAX_CONCURRENT_GAMES)


def load_app_ids(csv_path: str) -> list[int]:
    """Extracts app IDs from a CSV file automatically finding an 'appid' or 'app_id' column,

    or reading the first column.
    """
    if not os.path.exists(csv_path):
        print(f"Error: File '{csv_path}' not found.")
        sys.exit(1)

    app_ids = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)

        if not header:
            print(f"Error: File '{csv_path}' is empty.")
            sys.exit(1)

        # Check if the CSV has headers
        id_index = 0
        header_lower = [col.strip().lower() for col in header]
        for candidate in ["appid", "app_id", "id", "game_id"]:
            if candidate in header_lower:
                id_index = header_lower.index(candidate)
                break
        else:
            # If the first row wasn't a header, try parsing it as a number
            if header[0].strip().isdigit():
                app_ids.append(int(header[0].strip()))

        # Read remaining rows
        for row in reader:
            if row and len(row) > id_index:
                val = row[id_index].strip()
                if val.isdigit():
                    app_ids.append(int(val))

    print(f"Loaded {len(app_ids)} App IDs from '{csv_path}'.")
    return app_ids


async def process_game(app_id: int, session: aiohttp.ClientSession):
    async with semaphore:
        output_file = os.path.join(REVIEW_FOLDER, f"reviews_{app_id}_2025.csv")

        # Resume check: Skip games already downloaded
        if os.path.exists(output_file) and os.path.getsize(output_file) > 100:
            print(f"[{app_id}] File already exists. Skipping...")
            return

        print(f"[{app_id}] Starting review download...")
        cursor = "*"
        empty_strikes = 0
        total_downloaded = 0

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "voted_up", "votes_helpful", "text"])

            while True:
                url = f"https://store.steampowered.com/appreviews/{app_id}"
                params = {
                    "json": "1",
                    "filter": "recent",
                    "language": "english",
                    "num_per_page": "100",
                    "cursor": cursor,
                    "purchase_type": "all",
                    "review_type": "all",
                }

                try:
                    async with session.get(
                        url, params=params, timeout=15
                    ) as response:
                        if response.status == 429:
                            print(
                                f"[{app_id}] Rate limited (429). Waiting"
                                " 10s..."
                            )
                            await asyncio.sleep(10)
                            continue

                        if response.status != 200:
                            await asyncio.sleep(2)
                            continue

                        data = await response.json()
                except Exception as e:
                    print(f"[{app_id}] Connection error ({e}). Retrying...")
                    await asyncio.sleep(2)
                    continue

                if (
                    not data
                    or data.get("success") != 1
                    or not data.get("reviews")
                ):
                    empty_strikes += 1
                    if empty_strikes >= 3:
                        break
                    await asyncio.sleep(2)
                    continue

                empty_strikes = 0
                reviews = data["reviews"]
                reached_pre_2025 = False

                for review in reviews:
                    timestamp = review["timestamp_created"]

                    if timestamp > END_2025:
                        continue  # Skip 2026+ reviews
                    elif START_2025 <= timestamp <= END_2025:
                        date_str = datetime.fromtimestamp(timestamp).strftime(
                            "%Y-%m-%d"
                        )
                        text = (
                            review["review"]
                            .replace("\n", " ")
                            .replace("\r", "")
                            .strip()
                        )
                        if text:
                            writer.writerow(
                                [
                                    date_str,
                                    review["voted_up"],
                                    review["votes_up"],
                                    text,
                                ]
                            )
                            total_downloaded += 1
                    elif timestamp < START_2025:
                        reached_pre_2025 = True
                        break

                f.flush()  # Save progress immediately

                if reached_pre_2025:
                    print(
                        f"[{app_id}] Done! Saved {total_downloaded} reviews"
                        " from 2025."
                    )
                    break

                next_cursor = data.get("cursor")
                if not next_cursor or next_cursor == cursor:
                    break

                cursor = next_cursor
                await asyncio.sleep(0.2)


async def main(csv_path: str):
    app_ids = load_app_ids(csv_path)

    if not app_ids:
        print("No valid App IDs found to process.")
        return

    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [process_game(app_id, session) for app_id in app_ids]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape 2025 Steam reviews using App IDs from a CSV file."
    )
    parser.add_argument(
        "csv_path",
        type=str,
        help="Path to the CSV file containing game App IDs",
    )

    args = parser.parse_args()
    asyncio.run(main(args.csv_path))