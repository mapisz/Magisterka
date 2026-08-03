import argparse
import json
import os
import sys
import re
import time
import pandas as pd
from playwright.sync_api import sync_playwright

# Safely handle encoding reconfigurations across standard Python and Jupyter OutStream environments
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

OUTPUT_DIR = "./player_counts_2025"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sanitize_filename(name):
    """Clean game names for filesystem storage."""
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")

def download_steamdb_chart(appid, game_name="game", output_dir="./downloads", headless=False):
    """
    Downloads the player count Highcharts CSV data from SteamDB for a given App ID using sync_playwright.
    """
    url = f"https://steamdb.info/app/{appid}/charts/"
    safe_name = sanitize_filename(game_name)
    filepath = os.path.join(output_dir, f"{safe_name}_{appid}_player_counts.csv")
    user_data_dir = os.path.abspath("./browser_profile")
    os.makedirs(user_data_dir, exist_ok=True)
    
    print(f"\n[+] Processing: {game_name} (App ID: {appid})")
    print(f"    Target URL: {url}")
    
    with sync_playwright() as p:
        context = None
        for channel in ["chrome", "msedge", None]:
            try:
                kwargs = {
                    "user_data_dir": user_data_dir,
                    "headless": headless,
                    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                    "viewport": {"width": 1280, "height": 800}
                }
                if channel:
                    kwargs["channel"] = channel
                context = p.chromium.launch_persistent_context(**kwargs)
                break
            except Exception:
                continue
                
        if not context:
            print("    [X] Could not launch browser context.")
            return None
            
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            print(f"    HTTP Status: {response.status if response else 'Unknown'}")
            
            print("    Waiting for Highcharts container to load...")
            page.wait_for_selector(".highcharts-container, svg.highcharts-root, #chart-concurrent", timeout=25000)
            page.wait_for_timeout(3000)
            
            csv_data = None
            try:
                csv_data = page.evaluate("""() => {
                    if (window.Highcharts && window.Highcharts.charts) {
                        for (let chart of window.Highcharts.charts) {
                            if (chart && typeof chart.getCSV === 'function') {
                                return chart.getCSV();
                            }
                        }
                    }
                    return null;
                }""")
            except Exception as js_err:
                print(f"    [!] JS extraction fallback: {js_err}")
                
            if not csv_data:
                print("    Attempting UI export button download fallback...")
                export_btn = page.locator(".highcharts-exporting-group button, .highcharts-button-symbol")
                if export_btn.count() > 0:
                    export_btn.first.click()
                    page.wait_for_timeout(500)
                    
                    with page.expect_download(timeout=10000) as download_info:
                        csv_option = page.get_by_text("Download CSV", exact=False)
                        csv_option.click()
                    download = download_info.value
                    download.save_as(filepath)
                    print(f"    [OK] Saved CSV via download event: {filepath}")
                    context.close()
                    return filepath

            if csv_data and len(csv_data.strip()) > 0:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(csv_data)
                print(f"    [OK] Successfully downloaded and saved CSV: {filepath}")
                lines = csv_data.strip().split("\n")
                print(f"        Total CSV rows: {len(lines)}")
                print(f"        Header: {lines[0][:80]}")
                if len(lines) > 1:
                    print(f"        First row: {lines[1][:80]}")
            else:
                print(f"    [X] Could not retrieve CSV data for App ID {appid}.")

        except Exception as e:
            print(f"    [X] Error processing App ID {appid}: {e}")
        finally:
            page.close()
            context.close()
            
    return filepath

def run_batch_download(games_list, delay_seconds=4, output_dir=OUTPUT_DIR, headless=False):
    """
    Downloads charts for a list of games sequentially using synchronous Playwright.
    """
    results = []
    total = len(games_list)
    print(f"Starting batch download for {total} games...")
    
    for idx, item in enumerate(games_list, start=1):
        if isinstance(item, dict):
            appid = item.get("appid")
            name = item.get("name", f"App_{appid}")
        else:
            appid = int(item)
            name = f"App_{appid}"
            
        print(f"\n--- [{idx}/{total}] Processing: {name} (App ID: {appid}) ---")
        
        path = download_steamdb_chart(appid, game_name=name, output_dir=output_dir, headless=headless)
        results.append({"name": name, "appid": appid, "path": path})
        
        if idx < total:
            print(f"    Pausing {delay_seconds}s before next request...")
            time.sleep(delay_seconds)
            
    print("\n=========================================")
    print("Batch Download Complete!")
    print(f"Files saved in: {os.path.abspath(output_dir)}")
    return results

def download_games(app_ids, delay_seconds=4, output_dir=OUTPUT_DIR, headless=False):
    """
    Main function to call directly from Jupyter Notebook or Python scripts.
    """
    if isinstance(app_ids, (int, str)):
        games_list = [app_ids]
    else:
        games_list = list(app_ids)
        
    return run_batch_download(games_list, delay_seconds=delay_seconds, output_dir=output_dir, headless=headless)

def load_appids_from_file(filepath):
    """Loads App IDs from a JSON, CSV, or TXT file."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".json":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get("appids", list(data.values()))
    elif ext in [".csv", ".txt"]:
        df = pd.read_csv(filepath)
        if "appid" in df.columns:
            return df["appid"].tolist()
        elif len(df.columns) > 0:
            return df.iloc[:, 0].tolist()
    return []

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SteamDB Player Count Chart Downloader")
    parser.add_argument("--appids", nargs="+", help="Space-separated list of App IDs (e.g. 730 570 1086000)", default=None)
    parser.add_argument("--file", type=str, help="Path to JSON/CSV/TXT file containing App IDs or game dicts", default=None)
    parser.add_argument("--delay", type=int, default=4, help="Delay in seconds between downloads")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--output", type=str, default=OUTPUT_DIR, help="Output directory for CSV files")
    
    args = parser.parse_args()
    
    games_input = []
    if args.file and os.path.exists(args.file):
        games_input = load_appids_from_file(args.file)
    elif args.appids:
        games_input = args.appids
    else:
        # Default sample games if no arguments passed
        games_input = [730, 570]
        
    download_games(games_input, delay_seconds=args.delay, output_dir=args.output, headless=args.headless)
