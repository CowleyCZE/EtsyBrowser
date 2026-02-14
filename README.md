# Etsy Browser Bulk Uploader for StorkVisionArt

A Selenium-based automation tool for bulk uploading digital products to Etsy without using the official API.

## Features

- **Quick Edit Mode**: Auto-fill Etsy listing form from CSV data
- **Bulk Editor Mode**: Download Etsy CSV template, fill with data, upload back
- **Image Upload**: Drag&drop or file selector for up to 10 images per product
- **Smart Filling**: Category dropdown, auto-generated tags, price validation
- **Human-like Automation**: Random delays, scrolling, mouse movements to avoid bot detection

## Supported Etsy Fields

### Required
- title
- description (HTML)
- price
- quantity (999 for digital)
- images (up to 10)

### Categories
- Art&Collectibles > Prints > Digital Prints/WallArt

### Listing Status
- State: Active
- Who made: AI_GENERATED
- Is digital: YES

### Tags
- 13 auto-generated tags (e.g., "digital art, AI print, wall decor, modern art...")

### Shipping
- Digital download (no shipping required)

## Tech Stack

- Python 3.10+
- Selenium 4.15.2
- WebDriver Manager 4.0.1
- Pandas 2.1.4
- Pillow 10.1.0

## Project Structure

```
├── config.json          # Etsy credentials and settings
├── products.csv         # Source product data
├── requirements.txt     # Python dependencies
├── src/
│   ├── __init__.py
│   ├── browser_utils.py # Selenium browser setup and helpers
│   ├── fill_csv.py      # CSV filling utility
│   ├── logger.py        # Logging configuration
│   └── uploader.py      # Main uploader script
├── images/              # Product images directory
└── logs/                # Screenshots and error logs
```

## CSV Structure (products.csv)

```csv
title,description,price,tags,category_path,image_paths,shop_section
"Neon Cityscape Print","<b>AI-generated neon city digital print</b>. Instant download.",12.99,"digital art,neon,cityscape,modern,wall art,printable","Art&Collectibles:Prints:DigitalPrints","./images/neon01.jpg;./images/neon02.jpg","AI Digital Prints"
```

## Workflow

1. **START** → Login to etsy.com/your/shops/StorkVisionArt/manage
2. **MODE1 (Single)**: Add listing → fill form → upload images → Publish
3. **MODE2 (Bulk)**: Tools → Bulk Edit CSV → download template → fill → upload
4. **VALIDATION**: Check success → save listing_id → next product
5. **ERROR HANDLING**: Screenshot + retry 3x → skip → log
6. **FINISH**: Report (X/100 successful, time elapsed)

## Installation

```bash
git clone <repo>
pip install -r requirements.txt
cp config.example.json config.json  # Add email/password
python fill_csv.py  # Fill Etsy template from your CSV
python uploader.py --mode bulk --headless
```

## Configuration

Edit `config.json` with your Etsy credentials:

```json
{
  "etsy_url": "https://www.etsy.com/your/shops/StorkVisionArt/manage",
  "email": "your@email.com",
  "password": "your_password",
  "headless": false,
  "delay_min": 2,
  "delay_max": 10,
  "max_products_per_hour": 50
}
```

## Usage

### Single Product Mode
```bash
python uploader.py --mode single --product-id 1
```

### Bulk Mode
```bash
python uploader.py --mode bulk --headless
```

### With custom CSV
```bash
python uploader.py --csv custom_products.csv
```

## Advantages vs API

- ✅ No API approval required (works immediately)
- ✅ Supports variations, personalization, sale prices
- ✅ Etsy updates apply automatically
- ✅ Preview before publish

## Limitations & Solutions

### Bot Detection
- **Solution**: selenium-stealth, random user-agents, human delays

### Rate Limits (~10/min)
- **Solution**: 30s pause between products, max 50/hour

### Captcha
- **Solution**: 2FA backup login, manual intervention flag
