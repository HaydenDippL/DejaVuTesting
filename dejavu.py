import argparse
import sys
import json
import requests
from deepdiff import DeepDiff
from requests.packages.urllib3.exceptions import InsecureRequestWarning # type: ignore
import time
from colorama import Fore, Back, Style, init
import math
import os
from datetime import datetime
import pytz

class Discrepencies():
    def __init__(self):
        self.discrepencies = []
        self.failed = 0
        self.passed = 0

    def __len__(self):
        return len(self.discrepencies)
    
    def fail(self):
        self.failed += 1
    
    def success(self):
        self.passed += 1

    def add(self, attr, val, legacy_code, migrated_code):
        self.discrepencies.append([attr, val, legacy_code, migrated_code])

    def tablify(self, name):
        if self.__len__() > 0:
            table = "|Attributes|Input|Legacy|Migrated|\n"
            table += "|:-:|:-:|:-:|:-:|\n"
            for attr, val, legacy_code, migrated_code in self.discrepencies:
                val = '"' + val + '"' if type(val) == str else val
                table += f"|`{attr}`|`{val}`|{legacy_code}|{migrated_code}|\n"
            return table
        elif self.passed == 0 and self.failed == 0:
            return f"No testing done for **{name}**..."
        else:
            return f"No discrepencies found in the **{name} testing**..."

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
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

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
        if type(custom[keyword]) == list:
            return custom[keyword][0] if in_legacy else custom[keyword][1]
        else:
            return custom[keyword]
    else:
        return keyword

def get_stable_elements(data, in_legacy):
    result = {}

    for key, value in data.items():
        if type(value) == dict:
            result[key] = get_stable_elements(value, in_legacy)
        elif type(value) == list:
            result[key] = get_keyword_code(value[0], in_legacy)
        else:
            result[key] = get_keyword_code(value, in_legacy)

    return result

def remove_omit_keys(dict):
    omit_keys = [attr for attr, value in dict.items() if value == "$omit"]
    for key in omit_keys:
        del dict[key]

def get_stable_url(url, in_legacy):
    for path_pattern, path_variable in get_stable_elements(path, in_legacy=in_legacy).items():
        url = url.replace(path_pattern, str(path_variable))
    return url

def validate_input(config):
    if "custom" in config:
        global custom
        custom = config["custom"]
        validate_custom(custom)

    if "path" in config:
        global path
        path = config["path"]
        validate_path(path)

    if "query" in config:
        global query
        query = config["query"]
        validate_query(query)
    
    if "body" in config:
        global body
        body = config["body"]
        validate_body(body)

    if "headers" in config:
        global headers
        headers = config["headers"]

    if "endpoints" in config:
        global endpoints
        endpoints = config["endpoints"]
        validate_endpoints(endpoints)
    else:
        print(f"The endpoints attribute is required...")
        sys.exit()

def validate_custom(custom):
    # validate custom
    MIN_KEYWORD_SIZE = 2
    for keyword, options in custom.items():
        if len(keyword) < MIN_KEYWORD_SIZE or keyword[0] != '$':
            print(f"Custom keywords must be prefaced with '$' and cannot be less than {MIN_KEYWORD_SIZE} characters. The '{keyword}' in the custom attribute fails...")
            sys.exit()
        if type(options) != list or len(options) != 2:
            print(f"Custom values must be an array of size two. The value specified with '{keyword}': {options} in custom attribute fails...")
            sys.exit()

def validate_path(path):
    MIN_PATH_ATTR_SIZE = 2
    for attr, value in path.items():
        if type(attr) != str or len(attr) < MIN_PATH_ATTR_SIZE or not all(ch.isupper() for ch in attr[1:]):
            print(f"Path variables must be prefaced with a `@` and be atleast {MIN_PATH_ATTR_SIZE}. {attr} fails...")
            sys.exit()
        if type(value) != list or len(value) < 1:
            print(f"There must be atleast one option in the {attr} array in path...")
            sys.exit()
        for i, option in enumerate(value):
            if type(option) == str and len(option) > 0 and option[0] == '$' and not is_custom_or_special_function(option):
                print(f"Custom keywords like {option} in {attr} must be defined in the custom field...")
                sys.exit()
        if type(value) == list:
            path[attr] = preprocess(value)

def validate_query(query):
    for attr, options in query.items():
        for option in options:
            if type(option) == str and len(option) > 0 and option[0] == '$' and not is_custom_or_special_function(option) and option not in SPECIAL_CODES:
                print(f"Custom keywords like {option} in {attr} must be defined in the custom field...")
                sys.exit()
        if type(options) == list:
            query[attr] = preprocess(options)

def validate_body(body_sub, prefix=""):
    for attr, values in body_sub.items():
        attr_full = f"{prefix}.{attr}" if len(prefix) > 0 else f"{attr}"
        if type(values) == dict:
            validate_body(values, attr_full)
        elif type(values) == list:
            for option in values:
                if type(option) == str and len(option) > 0 and option[0] == '$' and not is_custom_or_special_function(option) and option not in SPECIAL_CODES:
                    print(f"Custom keywords like {attr_full} in {body} must be defined in custom attribute...")
                    sys.exit()
            body_sub[attr] = preprocess(values)
        elif type(values) == str:
            if type(option) == str and len(option) > 0 and option[0] == '$' and not is_custom_or_special_function(option) and option not in SPECIAL_CODES:
                print(f"Custom keywords like {attr_full} in {body} must be defined in custom attribute...")
                sys.exit()

def validate_endpoints(endpoints):
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
        global call_api
        if method == "GET": call_api = requests.get
        elif method == "POST": call_api = requests.post
        elif method == "PUT": call_api = requests.put
        elif method == "DELETE": call_api = requests.delete
        elif method == "PATCH": call_api = requests.patch
        elif method == "OPTIONS": call_api = requests.options
        elif method == "HEAD": call_api = requests.head

def is_custom_or_special_function(keyword):
    if keyword in custom:
        return True
    elif keyword[:6] == "$range":
        return True
    else:
        return False

def preprocess(options):
    remove = []
    ranges = []
    for i, keyword in enumerate(options):
        if type(keyword) == str and len(keyword) >= len("$range") and keyword[:6] == "$range":
            keyword = keyword.strip()
            args = [arg.strip() for arg in keyword[7:-1].split(",")]

            if len(args) < 2:
                pass
            if not args[0].isdigit() or not args[1].isdigit():
                pass
            start, end = int(args[0]), int(args[1])

            step = 1 if end > start else -1
            zfill = 0
            for arg in args[2:]:
                if len(arg) > len("step=") and arg[:5] == "step=" and arg[5:].strip().isdigit():
                    step = int(arg[5:].strip())
                elif len(arg) > len("zfill=") and arg[:6] == "zfill=" and arg[6:].strip().isdigit():
                    zfill = int(arg[6:].strip())

            my_range = range(start, end, step)
            if zfill != 0: my_range = [str(num).zfill(zfill) for num in my_range]

            remove.append(i)
            ranges.append(my_range)

    temp = 0
    for i, rng in zip(remove, ranges):
        options[i+temp:i+temp+1] = rng
        temp += len(rng) - 1

    return options

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
        verify=False
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
        json=migrated_stable_body,
        verify=False
    )

    if legacy_response.status_code // 100 != 2 or migrated_response.status_code // 100 != 2 or legacy_response.status_code != migrated_response.status_code:
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

def get_text_time_color(duration):
    YELLOW_SECONDS = 2
    RED_SECONDS = 5

    return Fore.GREEN if duration < YELLOW_SECONDS else Fore.YELLOW if duration < RED_SECONDS else Fore.RED

def get_text_code_color(code):
    code_class = code // 100
    if code_class == 1:
        return Fore.WHITE
    elif code_class == 2:
        return Fore.GREEN
    elif code_class == 3:
        return Fore.YELLOW
    elif code_class == 4:
        return Fore.RED
    else:
        return Fore.RED
    
def get_text_value(value):
    if value == None:
        return Fore.YELLOW + "null"
    if type(value) == int or type(value) == float:
        return Fore.MAGENTA + f"{value}"
    if type(value) == str:
        return Fore.WHITE + f'"{value}"'
    return Fore.WHITE + f"{value}"

def format_time(duration):
    SECONDS_IN_MINUTE = 60
    ONE_SECOND = 1
    MS_IN_SECOND = 1000

    if duration >= SECONDS_IN_MINUTE:
        minutes = math.floor(duration // SECONDS_IN_MINUTE)
        seconds = round(duration % SECONDS_IN_MINUTE)
        return f"{minutes} min {seconds} s"
    elif duration >= ONE_SECOND:
        return f"{duration:.2f} s"
    else:
        ms = duration * MS_IN_SECOND % MS_IN_SECOND
        return f"{ms:.0f} ms"

def run_test(legacy_url, migrated_url, attr, value, headers, legacy_params, migrated_params, legacy_body, migrated_body, discrepencies, verbose=True):
    TIME_JUST = 13
    CODE_JUST = 4
    CODE_MISMATCH_JUST = 40
    DISCREPENCIES_JUST = 15
    TIME_DIFF_JUST = 25
    print(Style.BRIGHT + f"{attr}: {get_text_value(value)}")

    print(f"\tLegacy:   ", end="")
    legacy_start = time.time()
    legacy_response = call_api(
        legacy_url,
        headers=headers,
        params=legacy_params,
        json=legacy_body,
        verify=False
    )
    legacy_duration = time.time() - legacy_start
    legacy_time_color = get_text_time_color(legacy_duration)
    legacy_formatted_time = format_time(legacy_duration)
    print(legacy_time_color + f"{legacy_formatted_time}".ljust(TIME_JUST), end="")

    legacy_status_color = get_text_code_color(legacy_response.status_code)
    print(legacy_status_color + f"{legacy_response.status_code}".ljust(CODE_JUST), end="\n")

    print(f"\tMigrated: ", end="")
    migrated_start = time.time()
    migrated_response = call_api(
        migrated_url,
        headers=headers,
        params=migrated_params,
        json=migrated_body,
        verify=False
    )
    migrated_duration = time.time() - migrated_start
    migrated_time_color = get_text_time_color(migrated_duration)
    migrated_formatted_time = format_time(migrated_duration)
    print(migrated_time_color + f"{migrated_formatted_time}".ljust(TIME_JUST), end="")

    migrated_status_color = get_text_code_color(migrated_response.status_code)
    print(migrated_status_color + f"{migrated_response.status_code}".ljust(CODE_JUST), end="")

    passed = True
    if legacy_response.status_code != migrated_response.status_code:
        print(Fore.RED + Style.BRIGHT + "CODE MISMATCH".rjust(CODE_MISMATCH_JUST), end="")
        discrepencies.add(attr, value, legacy_response.status_code, migrated_response.status_code)
        passed = False
    elif legacy_response.status_code == 200 and migrated_response.status_code == 200:
        passed = True
        legacy_response_json = json.loads(legacy_response.text)
        migrated_response_json = json.loads(migrated_response.text)
        diff = DeepDiff(legacy_response_json, migrated_response_json)

        removed = diff.get("dictionary_item_removed", {})
        if len(removed) > 0:
            print(Fore.RED + f"Removed: {len(removed)}".ljust(DISCREPENCIES_JUST), end="")
            passed = False
        else:
            print("".ljust(DISCREPENCIES_JUST), end="")
        for missing_attr in removed:
            discrepencies.add(attr, value, "", f"Missing: {missing_attr}")

        changes = {**diff.get("values_changed", {}), **diff.get("type_changes", {})}
        if len(changes) > 0:
            print(Fore.RED + f"Changed: {len(changes)}".ljust(DISCREPENCIES_JUST), end="")
            passed = False
        else:
            print("".ljust(DISCREPENCIES_JUST), end="")
        for changed_attr, change in changes.items():
            discrepencies.add(attr, value, f"Changed: {changed_attr} from {change['old_value']}", f"Changed: {changed_attr} to {change['new_value']}")
        
        THIRTY_SECONDS = 30 * 1000
        time_ratio = migrated_duration / legacy_duration
        if (migrated_duration >= 1.25 * legacy_duration or migrated_duration >  THIRTY_SECONDS + legacy_duration):
            print(Fore.RED + f"Time: +{format_time(migrated_duration - legacy_duration)} (x{time_ratio:.2f})".ljust(TIME_DIFF_JUST), end="")
            discrepencies.add(attr, value, legacy_formatted_time, f"{migrated_formatted_time} (x{time_ratio:.2f})")
            passed = False
        else:
            print("".ljust(TIME_DIFF_JUST), end="")

    if passed: discrepencies.success()
    else: discrepencies.fail()
    print()

def test_path():
    stable_legacy_params = get_stable_elements(query, in_legacy=True)
    stable_migrated_params = get_stable_elements(query, in_legacy=False)
    stable_legacy_body = get_stable_elements(body, in_legacy=True)
    stable_migrated_body = get_stable_elements(body, in_legacy=False)

    # Test URL and path variables
    path_discrepencies = Discrepencies()

    for path_pattern, path_variables in path.items():
        for path_variable in path_variables[1:]:
            temp_legacy_url = endpoints['legacy'].replace(path_pattern, str(get_keyword_code(path_variable, in_legacy=True)))
            temp_legacy_url = get_stable_url(temp_legacy_url, in_legacy=True)
            temp_migrated_url = endpoints['migrated'].replace(path_pattern, str(get_keyword_code(path_variable, in_legacy=False)))
            temp_migrated_url = get_stable_url(temp_migrated_url, in_legacy=False)

            run_test(temp_legacy_url, temp_migrated_url, path_pattern, path_variable, headers, stable_legacy_params, stable_migrated_params, stable_legacy_body, stable_migrated_body, path_discrepencies)

    return path_discrepencies

def test_query():
    stable_legacy_url = get_stable_url(endpoints['legacy'], in_legacy=True)
    stable_migrated_url = get_stable_url(endpoints['migrated'], in_legacy=False)
    stable_legacy_params = get_stable_elements(query, in_legacy=True)
    stable_migrated_params = get_stable_elements(query, in_legacy=False)
    stable_legacy_body = get_stable_elements(body, in_legacy=True)
    stable_migrated_body = get_stable_elements(body, in_legacy=False)

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

    return param_discrepencies

def test_body():
    stable_legacy_url = get_stable_url(endpoints['legacy'], in_legacy=True)
    stable_migrated_url = get_stable_url(endpoints['migrated'], in_legacy=False)
    stable_legacy_params = get_stable_elements(query, in_legacy=True)
    stable_migrated_params = get_stable_elements(query, in_legacy=False)
    stable_legacy_body = get_stable_elements(body, in_legacy=True)
    stable_migrated_body = get_stable_elements(body, in_legacy=False)

    body_sub = body.copy()

    body_discrepencies = Discrepencies()

    def test_body_recursively(legacy_sub, migrated_sub, body_sub, attr=""):
        for key, value in body_sub.items():
            if type(value) == list:
                for option in value[1:]:
                    legacy_sub[key] = get_keyword_code(option, in_legacy=True)
                    migrated_sub[key] = get_keyword_code(option, in_legacy=False)
                    if legacy_sub[key] == "$omit": del legacy_sub[key]
                    if migrated_sub[key] == "$omit": del migrated_sub[key]
                    run_test(
                        stable_legacy_url,
                        stable_migrated_url,
                        f"{attr}.{key}" if attr else f"{key}",
                        option,
                        headers,
                        stable_legacy_params,
                        stable_migrated_params,
                        stable_legacy_body,
                        stable_migrated_body,
                        body_discrepencies
                    )
                legacy_sub[key] = get_keyword_code(value[0], in_legacy=True)
                migrated_sub[key] = get_keyword_code(value[0], in_legacy=False)
                if legacy_sub[key] == "$omit": del legacy_sub[key]
                if migrated_sub[key] == "$omit": del migrated_sub[key]
            elif type(value) == dict:
                test_body_recursively(legacy_sub[key], migrated_sub[key], body_sub[key], f"{attr}.{key}" if attr else f"{key}")

    test_body_recursively(stable_legacy_body, stable_migrated_body, body_sub)
    return body_discrepencies

if __name__ == "__main__":
    start = time.time()

    parser = argparse.ArgumentParser(description="Process some JSON files.")
    parser.add_argument('config', type=str, help="Path to the JSON configuration file")
    args = parser.parse_args()

    init(autoreset=True)
    
    args.config = os.path.normpath(args.config)
    config = read_json(args.config)

    replicate_json = json.dumps(config, indent=4)

    validate_input(config)

    establish_baseline()

    path_discrepencies = test_path()
    param_discrepencies = test_query()
    body_discrepencies = test_body()

    total_discrepencies = len(path_discrepencies) + len(param_discrepencies) + len(body_discrepencies)
    tests_passed = path_discrepencies.passed + param_discrepencies.passed + body_discrepencies.passed
    tests_failed = path_discrepencies.failed + param_discrepencies.failed + body_discrepencies.failed
    total_tests = tests_passed + tests_failed
    total_tests_len = len(str(total_tests))

    end = time.time()

    print(Style.BRIGHT + f"\nTotal Execution Time: {format_time(end - start)}")
    print(Style.BRIGHT + f"Total Discrepencies: {total_discrepencies}")
    print(Style.BRIGHT + Fore.GREEN + f"Tests Passed: {f"{tests_passed}".ljust(total_tests_len)}")
    print(Style.BRIGHT + Fore.RED +   f"Tests Failed: {f"{tests_failed}".ljust(total_tests_len)}")
    print(Style.BRIGHT +              f"Total Tests:  {total_tests}")

    utc_now = datetime.now(pytz.utc)
    central_tz = pytz.timezone("America/Chicago")
    central_time = utc_now.replace(tzinfo=pytz.utc).astimezone(central_tz)

    formatted_time = central_time.strftime("%Y-%m-%d_%H;%M;%S")
    input_file_prefix, _ = os.path.splitext(os.path.basename(args.config))
    output_file = input_file_prefix + "-" + formatted_time + ".results.md"
    output_file_path = os.path.join("results", output_file)

    output = f"""# Results
This test was run on **{central_time.strftime("%b %d %I:%M %p %Y")}** and results sent to `{output_file}`.

**Tests Passed**: <span style="color: green;">{tests_passed} ({(100 * tests_passed / total_tests):.2f}%)</span>

**Tests Failed**: <span style="color: red;">{tests_failed} ({(100 * tests_failed / total_tests):.2f}%)</span>

**Total Execution Time**: {format_time(end - start)}

**Total Discrepencies**: {total_discrepencies}
            
## Path
{path_discrepencies.tablify("path")}
## Params
{param_discrepencies.tablify("params")} 
## Body
{body_discrepencies.tablify("body")}
# Replicate Me
This test was run on **{central_time.strftime("%b %d %I:%M %p %Y")}**

```
python dejavu.py {args.config}
```

### `{args.config}`
```json
{replicate_json}
```
"""

    with open(output_file_path, 'w') as file:
        file.write(output)

    with open("results.md", "w") as file:
        file.write(output)