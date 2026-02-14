"""Fill Etsy CSV template from products.csv data."""

import argparse
import csv
from pathlib import Path

from src.logger import setup_logger

logger = setup_logger("fill_csv")

# Etsy CSV field mapping
ETSY_FIELDS = {
    "title": "title",
    "description": "description",
    "price": "price",
    "quantity": "quantity",
    "category": "category_path",
    "tags": "tags",
    "image": "image_urls",
    "shop_section": "shop_section_id",
    "state": "state",
    "who_made": "who_made",
    "is_customizable": "is_customizable",
    "is_digital": "is_digital",
    "file_data": "file_data",
    "processing_min": "processing_min",
    "processing_max": "processing_max",
}


DEFAULT_VALUES = {
    "quantity": 999,
    "state": "active",
    "who_made": "AI_GENERATED",
    "is_customizable": "false",
    "is_digital": "true",
    "processing_min": 1,
    "processing_max": 1,
}


def read_products_csv(csv_path: str) -> list[dict]:
    """Read products from CSV file.
    
    Args:
        csv_path: Path to products CSV file
        
    Returns:
        List of product dictionaries
    """
    products = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                products.append(row)
        
        logger.info(f"Loaded {len(products)} products from {csv_path}")
        return products
    
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_path}")
        raise
    except Exception as e:
        logger.error(f"Error reading CSV: {e}")
        raise


def generate_etsy_csv(products: list[dict], output_path: str) -> str:
    """Generate Etsy-compatible CSV from products.
    
    Args:
        products: List of product dictionaries
        output_path: Path for output CSV file
        
    Returns:
        Path to generated CSV file
    """
    # Etsy CSV columns
    fieldnames = [
        "title",
        "description",
        "price",
        "quantity",
        "category_path",
        "tags",
        "image_urls",
        "shop_section",
        "state",
        "who_made",
        "is_customizable",
        "is_digital",
        "file_data",
        "processing_min",
        "processing_max",
    ]
    
    try:
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for product in products:
                row = {}
                
                # Map required fields
                row['title'] = product.get('title', '')
                row['description'] = product.get('description', '')
                row['price'] = product.get('price', '9.99')
                row['quantity'] = product.get('quantity', DEFAULT_VALUES['quantity'])
                row['category_path'] = product.get('category_path', 'Art&Collectibles:Prints:DigitalPrints')
                row['tags'] = product.get('tags', '')
                row['image_urls'] = product.get('image_paths', '')
                row['shop_section'] = product.get('shop_section', '')
                
                # Set default values for Etsy
                row['state'] = DEFAULT_VALUES['state']
                row['who_made'] = DEFAULT_VALUES['who_made']
                row['is_customizable'] = DEFAULT_VALUES['is_customizable']
                row['is_digital'] = DEFAULT_VALUES['is_digital']
                row['file_data'] = ''
                row['processing_min'] = DEFAULT_VALUES['processing_min']
                row['processing_max'] = DEFAULT_VALUES['processing_max']
                
                # Clean up image paths (convert to URLs if local paths)
                if row['image_urls']:
                    # Replace semicolons with newlines for Etsy format
                    row['image_urls'] = row['image_urls'].replace(';', '\n')
                
                writer.writerow(row)
        
        logger.info(f"Generated Etsy CSV: {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"Error generating CSV: {e}")
        raise


def validate_products_csv(csv_path: str) -> bool:
    """Validate products CSV has required fields.
    
    Args:
        csv_path: Path to products CSV file
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['title', 'description', 'price']
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            
            missing = [field for field in required_fields if field not in headers]
            
            if missing:
                logger.error(f"Missing required fields: {missing}")
                return False
            
            # Check for at least one product
            if not any(reader):
                logger.error("CSV file is empty")
                return False
            
            logger.info("CSV validation passed")
            return True
    
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return False


def main():
    """Main entry point for fill_csv script."""
    parser = argparse.ArgumentParser(
        description="Fill Etsy CSV template from products data"
    )
    parser.add_argument(
        '--input', 
        default='products.csv',
        help='Input CSV file (default: products.csv)'
    )
    parser.add_argument(
        '--output', 
        default='etsy_listings.csv',
        help='Output Etsy CSV file (default: etsy_listings.csv)'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate input CSV without generating output'
    )
    
    args = parser.parse_args()
    
    # Validate input
    if not validate_products_csv(args.input):
        logger.error("Input CSV validation failed")
        return 1
    
    if args.validate_only:
        logger.info("Validation complete")
        return 0
    
    # Generate Etsy CSV
    try:
        products = read_products_csv(args.input)
        generate_etsy_csv(products, args.output)
        logger.info(f"Successfully generated {args.output} with {len(products)} products")
        return 0
    except Exception as e:
        logger.error(f"Failed to generate CSV: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
