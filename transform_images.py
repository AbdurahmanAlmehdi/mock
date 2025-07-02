#!/usr/bin/env python3


import json
import argparse
import os
import copy
import requests
import io
import urllib.parse
import time
from PIL import Image
from typing import Any, Dict, List, Union, Tuple, Optional


class ImageModelTransformer:

    IMAGE_FIELDS = {
        'image', 'small_img', 'slider_images', 'homeTabBarBackgroundImage',
        'sectionTabBackgroundImage', 'sectionBackgrondImg', 'influencer_pfp',
        'backgroundImage', 'banner_image', 'profile_image', 'thumbnail',
        'cover_image', 'logo', 'icon'
    }

    def __init__(self,
                 fetch_dimensions: bool = True,
                 cache_dimensions: bool = True,
                 convert_category_ids: bool = True):
      
        self.fetch_dimensions = fetch_dimensions
        self.cache_dimensions = cache_dimensions
        self.convert_category_ids = convert_category_ids
        self.dimension_cache: Dict[str, Tuple[
            Optional[int], Optional[int]]] = {} if cache_dimensions else {}
        self.category_cache: Dict[str, str] = {}
        self.wordpress_base_url = "https://www.mataaa.com"
        self.odoo_filter_url = "https://staging.mataaa.com/gateway/CatalogManagement/api/v1/Category/Filter"
        # Store main category items during transformation
        self.main_category_items = []

    def collect_main_category_items(self, components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

        main_category_items = []
        components_to_remove = []

        for i, component in enumerate(components):
            if component.get('layout') == 'banner':
                items = component.get('config', {}).get('items', [])
                has_main_categories = False
                

                if all(item.get('isMainCategory', False) for item in items):
                    has_main_categories = True
                    for item in items:
                        main_category_items.append({
                            'id': str(item.get('category')),
                            'image': item.get('image')
                        })
                    components_to_remove.append(i)


        for index in reversed(components_to_remove):
            components.pop(index)


        if main_category_items:
            components.insert(0, {
                'layout': 'mainCategoryList',
                'config': {
                    'categories': main_category_items
                }
            })

        return components

    def is_image_url(self, value: Any) -> bool:
       
        if not isinstance(value, str):
            return False


        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
                            '.svg')


        if any(value.lower().endswith(ext) for ext in image_extensions):
            return True


        image_patterns = [
            'cdn.digitaloceanspaces.com', 'amazonaws.com', 'cloudinary.com',
            'imgur.com', 'unsplash.com', '/images/', '/img/', '/media/',
            '/assets/'
        ]

        return any(pattern in value.lower() for pattern in image_patterns)

    def get_image_dimensions(
            self, image_url: str) -> Tuple[Optional[int], Optional[int]]:
  
        if not self.fetch_dimensions:
            return None, None


        if self.cache_dimensions and image_url in self.dimension_cache:
            return self.dimension_cache[image_url]

        try:
            headers = {
                'User-Agent':
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            print(f"Fetching dimensions for: {image_url}")


            response = requests.get(image_url,
                                    headers=headers,
                                    timeout=5,
                                    stream=True)
            response.raise_for_status()


            image_data = io.BytesIO(response.content)
            with Image.open(image_data) as img:
                width, height = img.size

            print(f"  → {width}x{height}")


            if self.cache_dimensions:
                self.dimension_cache[image_url] = (width, height)

            return width, height

        except Exception as e:
            print(f"Warning: Could not fetch dimensions for {image_url}: {e}")

            if self.cache_dimensions:
                self.dimension_cache[image_url] = (None, None)
            return None, None

    def create_image_model(self,
                           image_url: str,
                           width: Optional[int] = None,
                           height: Optional[int] = None) -> Dict[str, Any]:

        if width is None or height is None:
            fetched_width, fetched_height = self.get_image_dimensions(
                image_url)
            width = width or fetched_width
            height = height or fetched_height

        image_model = {'imageUrl': image_url}

        if width is not None:
            image_model['width'] = str(width)

        if height is not None:
            image_model['height'] = str(height)

        return image_model

    def get_wordpress_category_name(self, category_id: str) -> Optional[str]:

        try:
            url = f"{self.wordpress_base_url}/wp-json/wc/v2/products/categories"
            params = {
                "include": category_id,
                "consumer_key": "ck_7f162b671db8061d5e0ba7de15f865aebf9e13c3",
                "consumer_secret":
                "cs_a65c0e2c7771f9a64a317873754779ce964c3172"
            }

            print(f"  → Fetching WordPress category: {category_id}")
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    category_name = data[0].get("name", "")
                    print(f"    ✓ Found category: {category_name}")
                    return category_name
                else:
                    print(f"    ✗ No category found for ID: {category_id}")
                    return None
            else:
                print(
                    f"    ✗ WordPress API error {response.status_code} for category {category_id}"
                )
                return None

        except Exception as e:
            print(
                f"    ✗ Error fetching WordPress category {category_id}: {e}")
            return None

    def get_odoo_category_id(self, category_name: str) -> Optional[str]:

        try:
            encoded_name = urllib.parse.quote(category_name)
            url = f"{self.odoo_filter_url}?Name={encoded_name}"

            print(f"  → Searching Odoo for: {category_name}")
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" and data.get(
                        "data") and len(data["data"]) > 0:
                    matta_id = data["data"][0].get("mattaId")
                    if matta_id:
                        print(f"    ✓ Found Odoo mattaId: {matta_id}")
                        return str(matta_id)

                print(f"    ✗ No Odoo category found for: {category_name}")
                return None
            else:
                print(
                    f"    ✗ Odoo API error {response.status_code} for category: {category_name}"
                )
                return None

        except Exception as e:
            print(f"    ✗ Error searching Odoo category {category_name}: {e}")
            return None

    def convert_category_id(self, category_id: str) -> str:

        if not self.convert_category_ids:
            return category_id


        if category_id in self.category_cache:
            return self.category_cache[category_id]


        category_name = self.get_wordpress_category_name(category_id)

        if category_name is None:

            print(
                f"  → Category {category_id} not found in WordPress, keeping as-is"
            )
            self.category_cache[category_id] = category_id
            return category_id


        odoo_id = self.get_odoo_category_id(category_name)

        if odoo_id is None:

            print(f"  → Using placeholder for category: {category_name}")
            placeholder_id = "1139"
            self.category_cache[category_id] = placeholder_id
            return placeholder_id


        self.category_cache[category_id] = odoo_id
        return odoo_id

    def transform_value(self, key: str, value: Any) -> Any:


        if key.lower() in ['category', 'categoryid'] and isinstance(
                value, (str, int)):
            category_str = str(value)
            if category_str.isdigit():
                converted_id = self.convert_category_id(category_str)

                if isinstance(value, int):
                    try:
                        return int(converted_id)
                    except ValueError:
                        return converted_id
                return converted_id


        if isinstance(value, str):

            if key.lower() in [field.lower() for field in self.IMAGE_FIELDS
                               ] or self.is_image_url(value):
                return self.create_image_model(value)


        elif isinstance(value, list):
            transformed_list = []
            for item in value:
                if isinstance(item, str) and (key.lower() in [
                        field.lower() for field in self.IMAGE_FIELDS
                ] or self.is_image_url(item)):
                    transformed_list.append(self.create_image_model(item))
                else:

                    transformed_list.append(self.transform_data(item))
            return transformed_list


        elif isinstance(value, dict):
            return self.transform_data(value)


        return value

    def transform_data(self, data: Any) -> Any:
        if isinstance(data, dict):
            transformed = {}
            for key, value in data.items():

                if key == 'components' and isinstance(value, list):
                    transformed[key] = self.collect_main_category_items(
                        [self.transform_data(item) for item in value]
                    )
                else:
                    transformed[key] = self.transform_value(key, value)
            return transformed
        elif isinstance(data, list):
            return [self.transform_data(item) for item in data]
        else:
            return data

    def transform_json_file(self, input_file: str) -> Dict[str, Any]:

        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file '{input_file}' not found")

        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Malformed JSON in '{input_file}': {e}", e.doc, e.pos)


        data_copy = copy.deepcopy(data)


        return self.transform_data(data_copy)

    def transform_json_string(self, json_string: str) -> Dict[str, Any]:
        
        try:
            data = json.loads(json_string)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Malformed JSON string: {e}", e.doc,
                                       e.pos)


        data_copy = copy.deepcopy(data)


        return self.transform_data(data_copy)


def main():

    parser = argparse.ArgumentParser(
        description=
        'Transform image URL strings in JSON to ImageModel dictionary format')
    parser.add_argument('input_file', help='Path to the input JSON file')
    parser.add_argument(
        '-o',
        '--output',
        help='Path to the output JSON file (default: print to stdout)',
        default=None)
    parser.add_argument('--indent',
                        type=int,
                        default=2,
                        help='JSON output indentation (default: 2)')
    parser.add_argument(
        '--no-dimensions',
        action='store_true',
        help='Skip fetching image dimensions for faster processing')

    args = parser.parse_args()

    try:

        fetch_dimensions = not args.no_dimensions
        transformer = ImageModelTransformer(fetch_dimensions=fetch_dimensions,
                                            convert_category_ids=True)

        if transformer.convert_category_ids:
            print("Converting WordPress category IDs to Odoo IDs...")

        transformed_data = transformer.transform_json_file(args.input_file)


        output_path = args.output or "output.json"


        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(transformed_data,
                      f,
                      ensure_ascii=False,
                      indent=args.indent)

        print(f"Transformed JSON written to '{output_path}'")

        if transformer.convert_category_ids and transformer.category_cache:
            print(
                f"Category conversions: {len(transformer.category_cache)} categories processed"
            )


    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    except json.JSONDecodeError as e:
        print(f"JSON Error: {e}")
        return 1

    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
