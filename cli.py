# cli.py
import argparse
import pandas as pd
import sys
from scraper import GoogleMapsScraper, ScrapeMode
from pathlib import Path


# ANSI Color codes
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_header():
    """Print welcome header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("╔═══════════════════════════════════════════╗")
    print("║     🗺️  Google Maps Scraper v2.1           ║")
    print("║     Extract Reviews & Place Data          ║")
    print("║     by Asira                               ║")
    print("╚═══════════════════════════════════════════╝")
    print(f"{Colors.END}\n")

def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.END}")

def print_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.END}")

def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.END}")

def print_progress(current: int, total: int, mode: str, url: str):
    """Print progress indicator"""
    percentage = (current / total) * 100
    bar_length = 30
    filled = int(bar_length * current // total)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    mode_display = f"{Colors.CYAN}{mode.upper()}{Colors.END}"
    print(f"\r{Colors.YELLOW}[{bar}]{Colors.END} [{current}/{total}] {mode_display} → {url[:50]}...", end="", flush=True)

def run_cli():
    parser = argparse.ArgumentParser(
        description="Google Maps Scraper - Extract reviews & place data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Reviews mode (auto-converts URLs if needed):
    python3 main.py --mode reviews --input input.xlsx --output reviews.xlsx \\
      --fields username,rating,caption,relative_date

  Summary mode:
    python3 main.py --mode summary --input input.xlsx --output summary.xlsx \\
      --fields name,overall_rating,n_reviews,pelayanan_count
        """
    )

    parser.add_argument(
        "--mode",
        choices=["summary", "reviews", "rekapv2"],
        help="Scraping mode: 'summary' (place info) atau 'reviews' (ulasan)"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="File Excel input dengan kolom 'url'"
    )

    parser.add_argument(
        "--output",
        default="output.xlsx",
        help="File Excel output (default: output.xlsx)"
    )

    parser.add_argument(
        "--fields",
        help="Pilih field spesifik, contoh: name,overall_rating,n_reviews"
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip N reviews pertama (hanya untuk mode reviews)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Jalankan dengan browser visible (untuk debug)"
    )

    args = parser.parse_args()

    print_header()

    # Validasi arguments
    if args.mode:
        handle_scraping(args)
    else:
        parser.print_help()
        print_error("Gunakan --mode (summary/reviews)")
        sys.exit(1)

def handle_scraping(args):
    """Handle scraping dengan auto URL conversion otomatis"""
    print_info(f"Mode: {Colors.BOLD}{args.mode.upper()}{Colors.END}")
    print_info(f"Input: {Colors.BOLD}{args.input}{Colors.END}")
    print_info(f"Output: {Colors.BOLD}{args.output}{Colors.END}")
    
    if args.fields:
        fields_list = args.fields.split(",")
        print_info(f"Fields: {', '.join([f for f in fields_list])}")
    else:
        print_info("Fields: ALL (semua field)")
    
    if args.mode == "reviews":
        print_info("Auto-convert URLs: Enabled (jika diperlukan)")
    
    print("")
    
    try:
        df_urls = pd.read_excel(args.input)
    except Exception as e:
        print_error(f"Gagal baca input file: {e}")
        sys.exit(1)
    
    if 'url' not in df_urls.columns:
        print_error("File input harus memiliki kolom 'url'")
        sys.exit(1)

    if 'cab' not in df_urls.columns:
        print_error("File input harus memiliki kolom 'cab'")
        sys.exit(1)
    
    fields = [f.strip() for f in args.fields.split(",")] if args.fields else None
    mode = ScrapeMode(args.mode)
    results = []
    total = len(df_urls)
    
    print(f"{Colors.CYAN}Scraping {total} URLs...{Colors.END}\n")
    
    with GoogleMapsScraper(debug=args.debug) as scraper:
        for idx, row in df_urls.iterrows():
            url = row["url"]
            cab = row["cab"]
            print_progress(idx + 1, total, args.mode, url)
            
            try:
                data = scraper.scrape(
                    url=url,
                    cab=cab,
                    mode=mode,
                    fields=fields,
                    review_offset=args.offset
                )

                if mode == ScrapeMode.SUMMARY:
                    results.append(data)
                elif mode == ScrapeMode.REKAPV2:
                    results.append(data)
                else:
                    results.extend(data)
            
            except Exception as e:
                print(f"\n{Colors.RED}Error on URL {url}: {e}{Colors.END}")
                continue
    
    print("\n")
    
    if not results:
        print_error("Tidak ada data yang berhasil di-scrape!")
        sys.exit(1)
    
    result_df = pd.DataFrame(results)
    if args.output.endswith(".csv"):
        #simpan di home directory
        result_df.to_csv(Path.home() / args.output, index=False, sep="|")
    else:
        result_df.to_excel(Path.home() / args.output, index=False)

    print_success(f"Scraping selesai! {len(results)} items berhasil.")
    print_info(f"Output saved: {Colors.BOLD}{args.output}{Colors.END}")
    print(f"\n{Colors.GRAY}Lihat file Excel untuk hasil lengkap{Colors.END}\n")
