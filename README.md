# Etsy Browser Bulk Uploader

Automated Etsy product uploader for digital products (AI art prints) using Selenium WebDriver. This tool automates the process of uploading products to Etsy without requiring the official API.

## ⚠️ Important Disclaimer

**This tool violates Etsy's Terms of Service** regarding automation and bot detection. Use at your own risk. Etsy may:
- Flag your account for automated behavior
- Temporarily or permanently suspend your shop
- Require CAPTCHA verification

**Recommendation**: Use this tool sparingly and with long delays between operations to minimize detection risk.

## Features

- **Quick Edit Mode**: Automated single product upload
- **Bulk Upload Mode**: Upload multiple products from CSV
- **Human-like Automation**: Random delays, mouse movements, scroll behavior
- **Smart Filling**: Category selection, tags, price validation
- **Image Upload**: Support for up to 10 images per product
- **Error Handling**: Automatic retry, screenshots on failure

## Requirements

- Python 3.10+
- Google Chrome browser
- ChromeDriver (automatically managed)

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd etsy-uploader

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp config.json config.json.bak  # backup
# Edit config.json with your Etsy credentials
```

## Configuration

Edit `config.json` with your settings:

```json
{
    "etsy": {
        "shop_name": "YourShopName",
        "base_url": "https://www.etsy.com/your/shops/YourShopName/manage"
    },
    "credentials": {
        "email": "your@email.com",
        "password": "yourpassword"
    },
    "settings": {
        "headless": false,
        "max_retries": 3,
        "delay_between_products": 30,
        "min_delay": 2,
        "max_delay": 10
    }
}
```

## Usage

### Prepare Your Products

1. Add images to the `images/` folder
2. Edit `products.csv` with your product data

### Convert CSV to Etsy Format

```bash
cd src
python fill_csv.py --input ../products.csv --output etsy_template.csv --validate --preview
```

### Upload Products

**Bulk Mode (all products):**
```bash
python uploader.py --mode bulk --headless
```

**Single Product Mode:**
```bash
python uploader.py --mode single --product-id 0 --headless
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--mode` | Upload mode: `single` or `bulk` |
| `--headless` | Run browser in headless mode |
| `--product-id` | Product index for single mode (0-based) |
| `--csv` | Path to CSV file (default: products.csv) |
| `--start-index` | Starting index for bulk upload |
| `--config` | Path to config file |

## CSV Format

Your `products.csv` should have these columns:

| Column | Required | Description |
|--------|----------|-------------|
| title | Yes | Product title (max 140 chars) |
| description | Yes | Product description (HTML allowed) |
| price | Yes | Price in USD |
| tags | No | Comma-separated tags (max 13) |
| category_path | No | Category path (e.g., Art&Collectibles:Prints:DigitalPrints) |
| image_paths | No | Semicolon-separated image paths |
| shop_section | No | Shop section name |

## Project Structure

```
etsy-uploader/
├── config.json          # Configuration (edit with your credentials)
├── products.csv         # Your product data
├── requirements.txt     # Python dependencies
├── src/
│   ├── uploader.py      # Main uploader script
│   ├── fill_csv.py      # CSV conversion tool
│   ├── browser_utils.py # Human-like automation
│   └── logger.py        # Logging utilities
├── logs/                # Error logs and screenshots
└── images/             # Product images
```

## Known Issues

### Bot Detection
If Etsy detects bot activity:
- Enable 2FA on your Etsy account
- Increase delays in config.json
- Run in non-headless mode occasionally
- Consider using proxy rotation

### Rate Limits
- Maximum ~10 uploads per minute
- Recommended: 30-60 seconds delay between products
- Maximum 50 products per hour

### CAPTCHA
If CAPTCHA appears:
- Log in manually first
- Enable 2FA
- Use non-headless mode

## Alternatives to Consider

Instead of this tool, consider:
1. **Etsy API**: Official API (requires approval)
2. **Printful/Printify**: Auto-sync with your shop
3. **Etsy Seller Tools**: Official bulk editing tools
4. **Drafts**: Use Etsy Teams for automation discussions

## License

MIT License - Use at your own risk.

## Support

This project is for educational purposes. The maintainer is not responsible for any Etsy account issues resulting from its use.
