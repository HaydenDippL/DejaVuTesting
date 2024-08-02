import argparse
import sys
import json
import requests
from deepdiff import DeepDiff

# TODO: include $omit functionality
# TODO: maybe add recursive testing?

class Discrepencies():
    def __init__(self):
        self.discrepencies = []

    def __len__(self):
        return len(self.discrepencies)

    def add(self, attr, val, legacy_code, migrated_code):
        self.discrepencies.append([attr, val, legacy_code, migrated_code])

    def tablify(self):
        table = "|Attributes|Input|Legacy|Migrated|\n"
        table += "|:-:|:-:|:-:|:-:|\n"
        for attr, val, legacy_code, migrated_code in self.discrepencies:
            val = '"' + val + '"' if type(val) == str else val
            table += f"|`{attr}`|`{val}`|{legacy_code}|{migrated_code}|\n"
        table += "\n"
        return table

SPECIAL_CODES = ["$omit"]

custom = {}
path = {}
query = {}
body = {}
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json"
}
endpoints = {}

config = {}

# Appropiate requests API function eg. requests.get, requests.post, etc...
call_api = None

def read_json(file_path):
    try:
        with open(file_path, 'r') as file:
            json_contents = json.load(file)
    except json.JSONDecodeError as e:
        print(f"There was an error reading the file {file_path}. Ensure that this file is JSON formatted. Paste your file into https://jsonlint.com/ to find errors")
        sys.exit()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit()

    return json_contents

def get_keyword_code(keyword, in_legacy):
    if type(keyword) == str and keyword in custom:
        if type(custom.keyword) == list:
            return custom.keyword[0] if in_legacy else custom.keyword[1]
        else:
            return custom.keyword
    else:
        return keyword

def get_stable_elements(dict, in_legacy):
    return {
        key: value[0] if key not in custom else get_keyword_code(key, in_legacy) 
        for key, value in dict.items()
    }

def remove_omit_keys(dict):
    omit_keys = [attr for attr, value in dict.items() if value == "$omit"]
    for key in omit_keys:
        del dict[key]

def get_stable_url(url, in_legacy):
    for path_pattern, path_variable in get_stable_elements(path, in_legacy=in_legacy).items():
        url = url.replace(path_pattern, str(path_variable))
    return url

def establish_baseline():
    legacy_url = endpoints['legacy']
    for path_match, path_variable in get_stable_elements(path, in_legacy=False).items():
        legacy_url = legacy_url.replace(path_match, str(path_variable))
    legacy_stable_query = get_stable_elements(query, in_legacy=True)
    legacy_stable_body = get_stable_elements(body, in_legacy=True)
    remove_omit_keys(legacy_stable_query)
    remove_omit_keys(legacy_stable_body)

    legacy_response = call_api(
        legacy_url, 
        headers=headers,
        params=legacy_stable_query,
        json=legacy_stable_body,
    )

    migrated_url = endpoints['migrated']
    for path_match, path_variable in get_stable_elements(path, in_legacy=False).items():
        migrated_url = migrated_url.replace(path_match, str(path_variable))
    migrated_stable_query = get_stable_elements(query, in_legacy=False)
    migrated_stable_body = get_stable_elements(body, in_legacy=False)
    remove_omit_keys(migrated_stable_query)
    remove_omit_keys(migrated_stable_body)
    
    migrated_response = call_api(
        migrated_url,
        headers=headers,
        params=migrated_stable_query,
        json=migrated_stable_body   
    )

    if legacy_response.status_code != 200 or migrated_response.status_code != 200:
        if legacy_response.status_code != 200:
            print(f"""Legacy responded to the stable call with a {legacy_response.status_code} when a 200 is required...
                  Url: {legacy_url}
                  Headers: {headers}
                  Params: {legacy_stable_query}
                  Body: {legacy_stable_body}
            """)
        if migrated_response.status_code != 200:
            print(f"""Migrated responded to the stable call with a {migrated_response.status_code} when a 200 is required...
                  Url: {migrated_url}
                  Headers: {headers}
                  Params: {migrated_stable_query}
                  Body: {migrated_stable_body}
            """)
        sys.exit()

def run_test(legacy_url, migrated_url, attr, value, headers, legacy_params, migrated_params, legacy_body, migrated_body, discrepencies):
    legacy_response = call_api(
        legacy_url,
        headers=headers,
        params=legacy_params,
        json=legacy_body
    )

    migrated_response = call_api(
        migrated_url,
        headers=headers,
        params=migrated_params,
        json=migrated_body
    )

    if legacy_response.status_code != migrated_response.status_code:
        discrepencies.add(attr, value, legacy_response.status_code, migrated_response.status_code)
    elif legacy_response.status_code == 200 and migrated_response.status_code == 200:
        legacy_response_json = json.loads(legacy_response.text)
        migrated_response_json = json.loads(migrated_response.text)
        diff = DeepDiff(legacy_response_json, migrated_response_json)
        for attr in diff.get("dictionary_item_removed", {}):
            discrepencies.add(attr, "Missing", "", "")
        for attr, change in diff.get("values_changed", {}).items():
            discrepencies.add(attr, "Changed", change['old_value'], change['new_value'])

def run_tests():
    # Initialize stable variables
    stable_legacy_url = get_stable_url(endpoints['legacy'], in_legacy=True)
    stable_migrated_url = get_stable_url(endpoints['migrated'], in_legacy=False)
    stable_legacy_params = get_stable_elements(query, in_legacy=True)
    stable_migrated_params = get_stable_elements(query, in_legacy=False)
    stable_legacy_body = get_stable_elements(body, in_legacy=True)
    stable_migrated_body = get_stable_elements(body, in_legacy=False)

    # Test URL and path variables
    path_discrepencies = Discrepencies()

    for path_pattern, path_variables in path.items():
        for path_variable in path_variables[1:]:
            temp_legacy_url = endpoints.legacy.replace(path_pattern, get_keyword_code(path_variable))
            temp_legacy_url = get_stable_url(temp_legacy_url, in_legacy=True)
            temp_migrated_url = endpoints.migrated.replace(path_pattern, get_keyword_code(path_variable))
            temp_migrated_url = get_stable_url(temp_migrated_url, in_legacy=False)

            run_test(temp_legacy_url, temp_migrated_url, path_pattern, path_variable, headers, stable_legacy_params, stable_migrated_params, stable_legacy_body, stable_migrated_body, path_discrepencies)

    # Test param queries
    param_discrepencies = Discrepencies()
    for attr, values in query.items():
        unstable_legacy_params = stable_legacy_params.copy()
        unstable_migrated_params = stable_migrated_params.copy()
        for value in values[1:]:
            unstable_legacy_params[attr] = get_keyword_code(value, in_legacy=True)
            unstable_migrated_params[attr] = get_keyword_code(value, in_legacy=False)
            remove_omit_keys(unstable_legacy_params)
            remove_omit_keys(unstable_migrated_params)

            run_test(stable_legacy_url, stable_migrated_url, attr, value, headers, unstable_legacy_params, unstable_migrated_params, stable_legacy_body, stable_migrated_body, param_discrepencies)

    # Test body
    body_discrepencies = Discrepencies()

    for attr, values in body.items():
        unstable_legacy_body = stable_legacy_body.copy()
        unstable_migrated_body = stable_migrated_body.copy()
        for value in values[1:]:
            unstable_legacy_body[attr] = get_keyword_code(value, in_legacy=True)
            unstable_migrated_body[attr] = get_keyword_code(value, in_legacy=False)
            remove_omit_keys(unstable_legacy_body)
            remove_omit_keys(unstable_migrated_body)

            run_test(stable_legacy_url, stable_migrated_url, attr, value, headers, stable_legacy_params, stable_migrated_params, unstable_legacy_body, unstable_migrated_body, body_discrepencies)
    
    return (path_discrepencies, param_discrepencies, body_discrepencies)

def generate_tables(path_discrepencies, param_discrepencies, body_discrepencies):
    output = ""

    total_path_options = 0
    for options in path.values():
        total_path_options += len(options)
    if len(path_discrepencies) > 0:
        output += path_discrepencies.tablify()
    elif len(path.items()) == total_path_options:
        output += "No testing done for **path**...\n\n"
    else:
        output += "No discrepencies found in the **path testing**...\n\n"

    total_param_options = 0
    for options in query.values():
        total_param_options += len(options)
    if len(param_discrepencies) > 0:
        output += param_discrepencies.tablify()
    elif len(query) == total_param_options:
        output += "No testing done for **params**...\n\n"
    else:
        output += "No discrepencies found in the **params testing**...\n\n"

    total_body_options = 0
    for options in body.values():
        total_body_options += len(options)
    if len(body_discrepencies) > 0:
        output += body_discrepencies
    elif len(body.items()) == total_body_options:
        output += "No testing done for **body**...\n\n"
    else:
        output += "No discrepencies found in the *body testing**...\n\n"

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some JSON files.")
    parser.add_argument('config', type=str, help="Path to the JSON configuration file")
    args = parser.parse_args()
    
    config = read_json(args.config)

    if "custom" in config:
        custom = config["custom"]

        # validate custom
        MIN_KEYWORD_SIZE = 2
        for keyword, options in custom.items():
            if len(keyword) < MIN_KEYWORD_SIZE or keyword[0] != '$':
                print(f"Custom keywords must be prefaced with '$' and cannot be less than {MIN_KEYWORD_SIZE} characters. The '{keyword}' in the custom attribute fails...")
                sys.exit()
            if type(options) != list or len(options) != 2:
                print(f"Custom values must be an array of size two. The value specified with '{keyword}': {options} in custom attribute fails...")
                sys.exit()

    if "path" in config:
        path = config["path"]

        EXPECTED_PARAM_FIELDS = ["path", "query"]
        MIN_PATH_ATTR_SIZE = 2
        for attr, value in path.items():
            if type(attr) != str or len(attr) < MIN_PATH_ATTR_SIZE or not all(ch.isupper() for ch in attr[1:]):
                print(f"Path variables must be prefaced with a `@` and be atleast {MIN_PATH_ATTR_SIZE}. {attr} fails...")
                sys.exit()
            if type(value) != list or len(value) < 1:
                print(f"There must be atleast one option in the {attr} array in path...")
                sys.exit()
            for option in value:
                if type(option) == str and option[0] == '$' and option not in custom:
                    print(f"Custom keywords like {option} in {attr} must be defined in the custom field...")
                    sys.exit()

    if "query" in config:
        query = config["query"]

        for attr, options in query.items():
            for option in options:
                if type(option) == str and len(option) > 0 and option[0] == '$' and option not in custom and option not in SPECIAL_CODES:
                    print(f"Custom keywords like {option} in {attr} must be defined in the custom field...")
                    sys.exit()

    if "body" in config:
        body = config["body"]
        # validate body
        for attr in body:
            for option in body[attr]:
                if type(option) == str and len(option) > 0 and option[0] == '$' and option not in custom and option not in SPECIAL_CODES:
                    print(f"Custom keywords like {option} in {body} must be defined in custom attribute...")
                    sys.exit()

    if "headers" in config:
        headers = config["headers"]

    if "endpoints" in config:
        endpoints = config["endpoints"]
        # validate format
        EXPECTED_ENDPOINT_FIELDS = ["legacy", "migrated", "method"]
        if len(endpoints.keys()) != len(EXPECTED_ENDPOINT_FIELDS) or not all(attr in endpoints.keys() for attr in EXPECTED_ENDPOINT_FIELDS):
            print(f"Expected {len(EXPECTED_ENDPOINT_FIELDS)} fields in endpoints attribute: {EXPECTED_ENDPOINT_FIELDS}...")
            sys.exit()
        if not all(type(value) == str for value in endpoints.values()):
            print(f"All values in endpoints attribute must be strings...")
            sys.exit()
        EXPECTED_ENDPOINT_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
        method = endpoints["method"].upper()
        if method not in EXPECTED_ENDPOINT_METHODS:
            print(f"The endpoint method in {endpoints} must be in {EXPECTED_ENDPOINT_FIELDS}, but {endpoints["method"]} was not...")
            sys.exit()
        else:
            if method == "GET": call_api = requests.get
            elif method == "POST": call_api = requests.post
            elif method == "PUT": call_api = requests.put
            elif method == "DELETE": call_api = requests.delete
            elif method == "PATCH": call_api = requests.patch
            elif method == "OPTIONS": call_api = requests.options
            elif method == "HEAD": call_api = requests.head
    else:
        print(f"The endpoints attribute is required...")
        sys.exit()
    
    establish_baseline()

    path_discrepencies, param_discrepencies, body_discrepencies = run_tests()

    output = generate_tables(path_discrepencies, param_discrepencies, body_discrepencies)

    print(output)
    with open("results.md", 'w') as file:
        file.write(output)