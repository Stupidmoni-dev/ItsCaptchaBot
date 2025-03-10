# import everything what we need
import glob
import os
import yaml
from functools import lru_cache


def read_yaml(file_path):
    # Read YAML file and return its content
    with open(file_path, 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)
    return data


trans_data = {}  # dict to store translations


# Load all translation files
for file in glob.glob("translations/*.yaml"):
    ln = os.path.splitext(os.path.basename(file))[0]  # get language code from filename
    yaml_data = read_yaml(file)  # read file
    trans_data[ln] = yaml_data  # save translations


def get_langs():
    # Return list of available languages
    return tuple(trans_data.keys())


class Translator:
    # Class for getting translations
    def __init__(self, lang, data):
        self.lang = lang
        self.data = data
    
    def __call__(self, key, default="Error: translation not found!") -> str:
        # Return translation by key or default message
        return self.data.get(key, default)


@lru_cache
def get_translator(lang):
    # Get Translator instance (cached)
    return Translator(lang, trans_data[lang])


def tr(obj, from_obj=False):
    # Auto-select language based on user data
    if not from_obj:
        obj = obj.from_user
    lang = obj.language_code if obj.language_code in get_langs() else 'en'
    return get_translator(lang)
