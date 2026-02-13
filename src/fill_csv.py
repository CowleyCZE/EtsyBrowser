#!/usr/bin/env python3
"""
Fill CSV Script
Converts product data from custom CSV to Etsy CSV template format.

Usage:
    python fill_csv.py
    python fill_csv.py --input products.csv --output etsy_template.csv
"""

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd


class EtsyCSVBuilder:
    """Build Etsy-compatible CSV from product data."""
    
    # Etsy CSV template headers
    ETSY_HEADERS = [
        'title',
        'description',
        'price',
        'quantity',
        'category_id',
        'tags',
        'who_made',
        'is_supply',
        'when_made',
        'item_weight',
        'item_weight_unit',
        'item_length',
        'item_width',
        'item_height',
        'item_dimensions_unit',
        'shipping_template_id',
        'image_1',
        'image_2',
        'image_3',
        'image_4',
        'image_5',
        'image_6',
        'image_7',
        'image_8',
        'image_9',
        'image_10',
        'shop_section_id'
    ]
    
    def __init__(self):
        self.products = []
        
    def load_products(self, csv_path: str) -> List[Dict[str, Any]]:
        """Load products from CSV file."""
        try:
            df = pd.read_csv(csv_path)
            products = df.to_dict('records')
            print(f"✓ Loaded {len(products)} products from {csv_path}")
            return products
        except Exception as e:
            print(f"✗ Failed to load CSV: {e}")
            return []
    
    def parse_image_paths(self, image_paths: str) -> List[str]:
        """Parse image paths from semicolon-separated string."""
        if not image_paths:
            return []
        return [p.strip() for p in image_paths.split(';') if p.strip()]
    
    def parse_tags(self, tags: str) -> str:
        """Parse and validate tags (max 13)."""
        if not tags:
            return ''
        
        tag_list = [t.strip() for t in tags.split(',')]
        
        # Limit to 13 tags (Etsy max)
        tag_list = tag_list[:13]
        
        return ','.join(tag_list)
    
    def transform_product(self, product: Dict[str, Any], defaults: Dict[str, Any] = None) -> Dict[str, Any]:
        """Transform product data to Etsy CSV format."""
        defaults = defaults or {}
        
        # Parse images
        images = self.parse_image_paths(product.get('image_paths', ''))
        
        # Transform to Etsy format
        etsy_product = {
            'title': product.get('title', ''),
            'description': product.get('description', ''),
            'price': product.get('price', ''),
            'quantity': product.get('quantity', defaults.get('quantity', 999)),
            'category_id': '',  # Will be filled by Etsy
            'tags': self.parse_tags(product.get('tags', '')),
            'who_made': defaults.get('who_made', 'AI_GENERATED'),
            'is_supply': 'false',
            'when_made': defaults.get('when_made', '2020_2024'),
            'item_weight': '',
            'item_weight_unit': '',
            'item_length': '',
            'item_width': '',
            'item_height': '',
            'item_dimensions_unit': '',
            'shipping_template_id': '',  # Use default
            'shop_section_id': '',
        }
        
        # Add images (up to 10)
        for i in range(10):
            if i < len(images):
                etsy_product[f'image_{i+1}'] = images[i]
            else:
                etsy_product[f'image_{i+1}'] = ''
        
        # Add shop section
        etsy_product['shop_section_id'] = product.get('shop_section', '')
        
        return etsy_product
    
    def create_etsy_csv(self, products: List[Dict[str, Any]], 
                        output_path: str, defaults: Dict[str, Any] = None) -> bool:
        """Create Etsy-compatible CSV file."""
        try:
            # Transform products
            etsy_products = []
            for product in products:
                transformed = self.transform_product(product, defaults)
                etsy_products.append(transformed)
            
            # Write to CSV
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.ETSY_HEADERS)
                writer.writeheader()
                writer.writerows(etsy_products)
            
            print(f"✓ Created Etsy CSV: {output_path}")
            print(f"  Total products: {len(etsy_products)}")
            return True
            
        except Exception as e:
            print(f"✗ Failed to create CSV: {e}")
            return False
    
    def validate_products(self, products: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Validate products and return warnings/errors."""
        warnings = []
        errors = []
        
        required_fields = ['title', 'description', 'price']
        
        for i, product in enumerate(products):
            # Check required fields
            for field in required_fields:
                if not product.get(field):
                    errors.append(f"Product {i+1}: Missing {field}")
            
            # Check title length
            title = product.get('title', '')
            if len(title) > 140:
                warnings.append(f"Product {i+1}: Title too long ({len(title)} chars)")
            
            # Check price
            try:
                price = float(product.get('price', 0))
                if price <= 0:
                    warnings.append(f"Product {i+1}: Invalid price")
            except:
                errors.append(f"Product {i+1}: Invalid price format")
            
            # Check tags
            tags = product.get('tags', '')
            if tags:
                tag_count = len([t for t in tags.split(',') if t.strip()])
                if tag_count > 13:
                    warnings.append(f"Product {i+1}: Too many tags ({tag_count})")
            
            # Check images
            images = self.parse_image_paths(product.get('image_paths', ''))
            for img in images:
                if not os.path.exists(img):
                    warnings.append(f"Product {i+1}: Image not found: {img}")
        
        return {
            'warnings': warnings,
            'errors': errors
        }
    
    def generate_preview(self, products: List[Dict[str, Any]], count: int = 5):
        """Generate a preview of products."""
        print("\n📋 Product Preview:")
        print("=" * 80)
        
        for i, product in enumerate(products[:count]):
            print(f"\n[{i+1}] {product.get('title', 'Untitled')[:50]}")
            print(f"    Price: ${product.get('price', 0)}")
            print(f"    Tags: {product.get('tags', '')[:60]}...")
            print(f"    Images: {product.get('image_paths', 'None')[:60]}...")
        
        if len(products) > count:
            print(f"\n... and {len(products) - count} more products")
        
        print("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Fill Etsy CSV Template')
    parser.add_argument('--input', '-i', default='../products.csv',
                        help='Input CSV file')
    parser.add_argument('--output', '-o', default='etsy_template.csv',
                        help='Output Etsy CSV file')
    parser.add_argument('--preview', '-p', action='store_true',
                        help='Show preview of products')
    parser.add_argument('--validate', '-v', action='store_true',
                        help='Validate products before creating CSV')
    
    args = parser.parse_args()
    
    # Create builder
    builder = EtsyCSVBuilder()
    
    # Load products
    products = builder.load_products(args.input)
    
    if not products:
        print("✗ No products to process")
        sys.exit(1)
    
    # Preview
    if args.preview:
        builder.generate_preview(products)
    
    # Validate
    if args.validate:
        print("\n🔍 Validating products...")
        validation = builder.validate_products(products)
        
        if validation['errors']:
            print("\n❌ ERRORS:")
            for error in validation['errors']:
                print(f"  - {error}")
        
        if validation['warnings']:
            print("\n⚠️  WARNINGS:")
            for warning in validation['warnings']:
                print(f"  - {warning}")
        
        if validation['errors']:
            print("\n✗ Validation failed. Fix errors before continuing.")
            sys.exit(1)
        else:
            print("✓ Validation passed!")
    
    # Default settings
    defaults = {
        'quantity': 999,
        'who_made': 'AI_GENERATED',
        'when_made': '2020_2024'
    }
    
    # Create CSV
    success = builder.create_etsy_csv(products, args.output, defaults)
    
    if success:
        print(f"\n✅ Done! Output saved to: {args.output}")
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
