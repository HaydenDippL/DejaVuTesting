# DejaVu Testing

DejaVu testing is an CLI for testing API migrations and modernizations. It allows you to interatively compare and contrast two endpoints and test efficiently.

Please read through **WALKTHROUGH** and **THINGS TO KNOW** for a *mostly* complete understanding of how to operate this system. You can ignore **DOCUMENTATION** 😁😁, unless you really get stuck.

**Usage**
```
python3 dejavu.py config.json
```

# Walkthrough

## Setup

Example: you are testing two POST endpoints that use two body fields `id` and `name`. You want to see what happens in each endpoint, legacy and migrated, if you input `id` with `908303034499` or `"9083033499"` and what happens if you input `name` with `"Hayden"` or `null` or `""`. The way that you would do this is simple. First you would create the `config.json` file in the working directory...

```json
{
    "body": {
        "id": [9083033499, "9083033499"],
        "name": ["Hayden" null, ""],
        "nickname": "Sleepy"
    },
    "endpoints": {
        "legacy": "https://your-legacy-endpoint.com",
        "migrated": "https://your-migrated-endpoint.com",
        "method": "PUT"
    }
}
```

Let's break it down. The `config.json` file can have up to 6 fields: [`path`](#path), [`query`](#query), [`endpoints`](#endpoints), [`custom`](#custom), [`body`](#body), and [`headers`](#headers). In the example above we use `body` and `endpoints` to define our call. You'll notice that `body` has array values. This is because we will iterate through these values, testing them all. 

The easiest way to explain this is via example.

```
python3 dejavu.py config.json
```

## Baseline Test


The first thing that the CLI will do is run a baseline test with the <u>stable elements</u>. The <u>stable elements</u> are all first elemnts in the arrays and primitive values. The first call to legacy and migrated will have this <u>stable body</u>.

```json
{
    "id": 9083033499,
    "name": "Hayden",
    "nickname": "Sleepy"
}
```

The first element of the `body.id` array is `9083033499` and `body.name` array is `"Hayden"`. We will use these values in our call. Because `body.nickname` is a primitive value - `int`, `double`, `null`, or `string` (not nested objects and arrays) - `"Sleepy"` is used.

To pass the baseline test, the legacy and migrated urls must both return the same response code in the 200s to this request. If this test fails, then the program terminates prematurely. 

## Testing

Now that the baseline test has passed, the real testing can begin. The first body that we will test is...

```json
{
    "id":  "9083033499",
    "name": "Hayden",
    "nickname": "Sleepy"
}
```

The difference from the baseline test is that `id` is no longer a stable element. It is now the second option from `body.id`: `"9083033499"`. Notice that only one item has changed from the baseline (which we know works). This ensures that a change in response is solely due to the change of this one option.

We send the request to both legacy and migrated and get a status code of `200` in legacy and a status code of `300` in migrated. The CLI will remember this information and other discrepencies when it generates the report

The next query the CLI test is...

```json
{
    "id": 9083033499,
    "name": null,
    "nickname": "Sleepy"
}
```

Notice now that because we have exhausted all the options in the `body.id` array, we have gone back to the <u>stable</u> `id` and are now experimenting with the `name` field (`null`). This ensures that the changes in status code are only due to this variation in the `name` field. Say legacy gets a `200` and migrated gets a `200`.

The final test the CLI runs is with this query

```json
{
    "id": 9083033499,
    "name": "",
    "nickname": "Sleepy"
}
```

We have now iterated to the final `name`  option `""`, the empty string, and we receive a `400` code from legacy and a `200` code from migrated.

Notice that the CLI never ran any tests changing `body.nickname` as this was a set primitive value.

The final order of business is to generate the report.

---

The CLI will automatically create a markdown table report of its findings. To recap:
- `"id":  "9083033499"`, *with all else equal*, gave legacy `200` and migrated `300`
- `"name": null`, *with all else equal*, gave legacy `200` and migrated `200`
- `"name": ""`, *with all else equal*, gave legacy `400` and migrated `200`

The report that the CLI would produce in the console in markdown form would be:

| Attributes | Input | Legacy | Migrated |
|:-:|:-:|:-:|:-:|
|`id`|`"9083033499"`|200|300|
|`name`|`""`|400|200|

This table will show the differences between the endpoints. Notice that the CLI excludes the findings from the `"name": null` test as both legacy and migrated returned the same code: `200`. 

# Things to Know

The `body` can be a nested object and still be test. For example...

```json
"body": {
    "name": {
        "First": ["Hayden", "Thomas"],
        "Last": ["Dippel"]
    }
}
```

will test `"Hayden Dippel"` and `"Thomas Dippel"`.

---

You can define **disjoint** custom variables that send different value to legacy and migrated. For example...

```json
"custom": {
    "$date": ["08/23/2005", "2005-08-23"]
}
"body": {
    "birthday": "$date"
}
```

... sends a body with `"08/23/2005"` to legacy and a body with `'2005-08-23"` to migrated. See more details in [`custom`](#custom).

---

Using the `"$omit"` string in `body` and `query` will exclude that key-value pair in a test. For example... 

```json
"body": {
    "name": ["Hayden", "$omit"]
}
```

... will test two bodies: `{"name": "Hayden"}` and `{}`. You cannot use `"$omit"` in the `path` tests.

`"$omit"` and other special codes can be found [here](#special-codes)

---

You can set up and test path variables. See [`path`](#path).

---

You cannot test `headers`, everything specified in there is sent to the servers. Excluding the headers attribute in your config will automatically send these headers:

```json
"headers": {
    "Content-Type": "application/json",
    "Accept": "application/json"
}
```

---

This CLI will also check for differences in the response bodies from legacy and migrated. It will only report an error if a common field in the response bodies of legacy and migrated have different values (CHANGED) or if there is a field in legacy that is not in migrated (REMOVED). A field that is missing in legacy but produced in migrated (ADDED) is ignored.

# Documentation

## body

This **optional** json file would contain the different combinations of inputs that you would like to test. The format would look something like this...

```json
"body": {
    "id": [9083033499, "9083033499", -1, "", null, "$omit", "Hayden"],
    "name": ["Hayden", 12, "", null, "$omit"]
}
```

The first element of any options array must be a known valid input. This is to ensure that the program can have a known valid request that it can compare a potentially invalid request to. 

You may also notice the strings that start with `'$'`. These are special options which perform some other functionality. The `"$omit"` special option will send the request through without that field. In this case: the body would have just been...

```json
"body": {
    "name": "Hayden"
}
```

...as the `id` was ommited.

---

Body can also contain nested objects....

```json
"body": {
    "name": {
        "First": ["Hayden", "Thomas"],
        "Last": ["Dippel"]
    }
}
```

... will test `"Hayden Dippel"` and `"Thomas Dippel"`. Body is the only field which can contain nested objects.

---

If you want to pass an array and an option, you can use this syntax...

```json
"body": {
    "name": ["Hayden Dippel", ["Hayden", "Dippel"]]
}
```

## path

The path field is an **optional** field. Path paramters must always be prefaced with a `'@'` and be capitalized. If the path parameter key matches a segment of the url, its value array is used. **NOTE** that [custom](#custom) keywords can be defined for path variables also.

```json
"path": {
    "@ID": [9083033499]
}
```

If a legacy endpoint was defined as `"https://www.google.com/@ID"` the following json would reformat this as `"https://www.google.com/9083033499"`

## query

Query paramters are an **optional** field and work much in the same way as the body, except that it cannot contain nested objects.

```json
"query": {
    "name": ["Hayden"]
}
```

If a legacy endpoint was defined as `"https://www.google.com"` the following json would reformat this as `"https://www.google.com?name=Hayden"`

## headers

This is a **optional** field to specify the headers of your function. The are no combinations and this json is passed directly as your headers. An example of this file includes...

```json
"headers": {
    "Content-Type": "application/json",
    "Accept": "application/json"
}
```

This field is not required and if it is not passed, the above headers are used as the default.

## endpoints

This is a **required** json field to specify the endpoints that you will be hitting.

```json
"endpoints": {
    "legacy": "https://www.google.legacy.com",
    "migrated": "https://www.google.com",
    "method": "POST"
}
```

## custom

This file is for specifying custom special options in your project and is **optional**. This is for the scenario where the two endpoints accept slightly different data. An example is that the two endpoints accept different date formats "MM-DD-YYYY" and "MM/DD/YYYY". This allows you to specify one of these formats for legacy and one for migrated. For example:

```json
"custom": {
    "$date": ["12-21-2002", "12/21/2002"]
}
```

Legacy will always take the first element and migrated will always take the second. Now if you make this call in your `body` field.

```json
"body": {
    "date_of_birth": ["$date"]
}
```

Legacy will always take `"12-21-2002"` and migrated will always take `"12/21/2002"`, allowing always valid access on the first element on the combination array. 

You must always define these custom special options with a `"$"`. 

## Special Codes

Special codes are always a string that start with `"$"`. They can allow for complex functionality, random variables, and ranges of variables.

### `"$omit"`

Using the `"$omit"` string in `body` and `query` will exclude that key-value pair in a test. For example... 

```json
"body": {
    "name": ["Hayden", "$omit"]
}
```

... will test two bodies: `{"name": "Hayden"}` and `{}`. You cannot use `"$omit"` in the `path` tests.

### `"$range()"`

Range allows for iteration over a range of number". Range expects two int arguments and optionally a `step` and a `zfill` argument.

```python
"$range(0, 10)" # 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
```

```python
"$range(0, 10, step=2)" # 0, 2, 4, 6, 8
```

```python
"$range(0, 22, step=5, zfill=3)" # "000", "005", "010", "015", "020"
```