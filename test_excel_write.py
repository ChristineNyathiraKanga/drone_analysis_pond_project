"""
Test script to add sample data to SharePoint Excel table.
Run this to test the to_sheet_batch function with dummy data.
"""

import os
from reed_analyse import to_sheet_batch

def main():
    # Sample recommendation data
    sample_data = [
        {
            'Pond Identifier': 'Pond A',
            'observations': 'Green',
            'Recommendation': 'No action needed',
            'Pond Category': 'Category 1'
        },
        {
            'Pond Identifier': 'Pond B',
            'observations': 'Blue',
            'Recommendation': 'Need to fill',
            'Pond Category': 'Category 2'
        },
        {
            'Pond Identifier': 'Pond C',
            'observations': 'Red',
            'Recommendation': 'Urgent pond refill',
            'Pond Category': 'Category 1'
        }
    ]

    print("Testing SharePoint Excel write with sample data...")
    try:
        to_sheet_batch(sample_data)
        print("✅ Test successful! Data added to Excel.")
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == '__main__':
    main()
