import argparse
import os
import sys
import json
import requests

custom = {}
params = {}
body = {}
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json"
}
endpoints = {}

# Appropiate requests API function eg. requests.get, requests.post, etc...
call_api = None

def get_keyword_code(keyword, in_legacy):
    if type(custom.keyword) == list:
        return custom.keyword[0] if in_legacy else custom.keyword[1]
    else:
        return custom.keyword
    
def establish_baseline():
    def get_stable_elements(dict, in_legacy):
        return {
            key: value[0] if key not in custom else get_keyword_code(key, in_legacy) 
            for key, value in dict.items()
        }
    
    legacy_url = endpoints.legacy
    for path_match, path_variable in get_stable_elements(params.path, in_legacy=False).items():
        legacy_url.replace(path_match, path_variable)

    legacy_response = call_api(
        legacy_url, 
        headers=headers,
        params=get_stable_elements(params.query, in_legacy=True),
        body=get_stable_elements(body, in_legacy=True),
    )

    migrated_url = endpoints.migrated
    for path_match, path_variable in get_stable_elements(params.path, in_legacy=False).items():
        migrated_url = migrated_url.replace(path_match, path_variable)
    
    migrated_response = call_api(
        migrated_url,
        headers=headers,
        params=get_stable_elements(params.query, in_legacy=False),
        body=get_stable_elements(body, in_legacy=False)   
    )

    if legacy_response.status_code != 200 or migrated_response.status_code != 200:
        if legacy_response.status_code != 200:
            print(f"""Legacy responded to the stable call with a {legacy_response.status_code} when a 200 is required...
                  Url: {legacy_url}
                  Headers: {headers}
                  Params: {get_stable_elements(params.query)}
                  Body: {get_stable_elements(body)}
            """)
        if migrated_response.status_code != 200:
            print(f"""Migrated responded to the stable call with a {migrated_response.status_code} when a 200 is required...
                  Url: {migrated_url}
                  Headers: {headers}
                  Params: {get_stable_elements(params.query)}
                  Body: {get_stable_elements(body)}
            """)
        sys.exit()
            
def run_tests():
    pass

def generate_table():
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some JSON files.")

    parser.add_argument("-p", "--params", type=str, required=False, help="Path to params.json")
    parser.add_argument("-b", "--body", type=str, required=False, help="Path to body.json")
    parser.add_argument("-H", "--headers", type=str, required=False, help="Path to headers.json")
    parser.add_argument("-e", "--endpoints", type=str, required=True, help="Path to endpoints.json")
    parser.add_argument("-c", "--custom", type=str, required=False, help="Path to custom.json")

    args = parser.parse_args()

    def path_does_not_exist(path):
        print(f"The path `{path}` does not exist...")
        sys.exit()

    def read_json(path):
        try:
            with open(path, 'r') as file:
                json_contents = json.load(file)
        except:
            print(f"There was an error reading the file {path}. Ensure that this file is json formatted. Paste your file into https://jsonlint.com/ to find errors")
            sys.exit()
        return json_contents

    if args.custom and os.path.exists(args.custom):
        custom = read_json(args.custom)

        # validate custom
        MIN_KEYWORD_SIZE = 2
        for keyword, options in custom.items():
            if len(keyword) < MIN_KEYWORD_SIZE or keyword[0] != '$':
                print(f"Custom keywords must be prefaced with '$' and cannot be less than {MIN_KEYWORD_SIZE} characters. The '{keyword}' in `{args.custom}` fails...")
                sys.exit()
            if type(options) != list or len(options) != 2:
                print(f"Custom values must be an array of size two. The value specified with '{keyword}': {options} in `{args.custom}` fails...")
                sys.exit()
    elif args.custom:
        path_does_not_exist(args.custom)

    if args.params and os.path.exists(args.params):
        params = read_json(args.params)

        # validate params
        EXPECTED_PARAM_FIELDS = ["path", "query"]
        if len(params.keys()) != len(EXPECTED_PARAM_FIELDS) or not all(attr in params.keys() for attr in EXPECTED_PARAM_FIELDS):
            print(f"Expected {len(EXPECTED_PARAM_FIELDS)} fields: ${EXPECTED_PARAM_FIELDS}, but found ${params.keys()}...")
            sys.exit()
        MIN_PATH_ATTR_SIZE = 2
        for attr, value in params["path"].items():
            if type(attr) != str or len(attr) < MIN_PATH_ATTR_SIZE or not all(ch.isupper() for ch in attr[1:]):
                print(f"Path variables must be prefaced with a `@` and be atleast {MIN_PATH_ATTR_SIZE}. {attr} fails...")
                sys.exit()
            if type(value) != list or len(value) < 1:
                print(f"There must be atleast one option in the {attr} array in {args.params}...")
                sys.exit()
            for option in value:
                if type(option) == str and option[0] == '$' and option not in custom:
                    print(f"Custom keywords like {option} in {params} must be defined in ${args.params}...")
                    sys.exit()
        for attr in params["query"]:
            for option in params["query"][attr]:
                if type(option) == str and option[0] == '$' and option not in custom:
                    print(f"Custom keywords like {option} in {params} must be defined in {args.params}...")
                    sys.exit()
    elif args.params:
        path_does_not_exist(args.params)

    if args.body and os.path.exists(args.body):
        body = read_json(args.body)
        # validate body
        for attr in body:
            for option in body[attr]:
                if type(option) == str and option[0] == '$' and option not in custom:
                    print(f"Custom keywords like {option} in {body} must be defined in ${args.custom}...")
                    sys.exit()
    elif args.body:
        path_does_not_exist(args.body)

    if args.headers and os.path.exists(args.headers):
        headers = read_json(args.headers)
    elif args.headers:
        path_does_not_exist(args.headers)

    if os.path.exists(args.endpoints):
        endpoints = read_json(args.endpoints)
        # validate format
        EXPECTED_ENDPOINT_FIELDS = ["legacy", "migrated", "method"]
        if len(endpoints.keys()) != len(EXPECTED_ENDPOINT_FIELDS) or not all(attr in endpoints.key() for attr in EXPECTED_ENDPOINT_FIELDS):
            print(f"Expected {len(EXPECTED_ENDPOINT_FIELDS)} fields in {args.endpoints}: {EXPECTED_ENDPOINT_FIELDS}...")
            sys.exit()
        if not all(type(value) == str for value in endpoints.values()):
            print(f"All values in {args.endpoints} must be strings...")
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
        path_does_not_exist(args.endpoints)