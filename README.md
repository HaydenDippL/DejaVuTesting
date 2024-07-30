# DejaVu Testing

DejaVu testing is an CLI for testing API migrations and modernizations. It allows you to interatively compare and contrast two endpoints and test efficiently.

**Usage**

python3 dejavu.py<br/>
-p [params.json](#paramsjson)<br/>
-b [body.json](#bodyjson)<br/>
-h [headers.json](#headersjson)<br/>
-e [endpoints.json](#endpointsjson)<br/>
-c [custom.json](#customjson)<br/>

# Walkthrough

### Setup

Example: you are testing two endpoints that use two body fields `id` and `name`. You want to see what happens in each enpoint, legacy and migrated, if you input `id` with `908303034499` or `"9083033499"` and what happens if you input `name` with `"Hayden"` or `null` or `""`. The way that you would do this is simple. First you would create a `body.json` file in the working directory...

```json
{
    "id": [9083033499, "9083033499"],
    "name": ["Hayden" null, ""]
}
```

The first element in each array represents a **VALID, KNOWN** input for **BOTH** endpoints.

Next you would make a `endpoints.json` file that contains the endpoints...

```json
{
    "legacy": "https://your-legacy-endpoint.com",
    "migrated": "https://your-migrated-endpoint.com"
}
```

Then you would run the following command

```
python3 -b body.json -e endpoints.json
```

### Execution


First thing that the CLI does is run on both endpoints with the valid input on both endpoints. Remember that the first object in each array is a **VALID, KNOWN** input for **BOTH** both endpoints. The CLI runs a test with the following...

```json
{
    "id": 9083033499,
    "name": "Hayden"
}
```

If either test, running this query on legacy or migrated, returns a code other than 200, the program will fail. After it verifies a baseline, it will then begin iterativelty comparing and contrasting the two endpoints. It will first call legacy with

```json
{
    "id":  "9083033499",
    "name": "Hayden"
}
```

Notice that the id is no longer the baseline, but the first combination option that was specified in the body.json file. Say that it receives a code of `200`. The CLI then will run the same exact query on the migrated endpoint and say it receives a code of `300`. It will remember this information when it goes to report to you the findings. 

The next query the CLI test is 

```json
{
    "id": 9083033499,
    "name": null
}
```

Notice now that because we have exhausted all the options in the `id` combination array, we have gone back to the **KNOWN, VALID** `id` and are now experimenting with the `name` field (`null`). This ensures that the changes in status code are only due to this variation in the `name` field. Say legacy gets a `200` and migrated gets a `200`.

The final test the CLI runs is with this query

```json
{
    "id": 9083033499,
    "name": ""
}
```

We have now iterated to the final `id` combination option `""`, the empty string, and we receive a `400` code from legacy and a `200` code from migrated. The next order of business of the CLI is to create a report.

---

The CLI will automatically create a markdown table report of its findings. To recap:
- `"id":  "9083033499"` gave legacy `200` and migrated `300`
- `"name": null` gave legacy `200` and migrated `200`
- `"name": ""` gave legacy `400` and migrated `200`

The report that the CLI would produce in the console in markdown form would be:

| Attributes | Input | Legacy | Migrated |
|:-:|:-:|:-:|:-:|
|`id`|`"9083033499"`|200|300|
|`name`|`""`|400|200|

This table will show the differences between the endpoints. Notice that the CLI excludes the findings from the `"name": null` test as both legacy and migrated returned the same code: `200`. 

# Documentation

## body.json

This **required** json file would contain the different combinations of inputs that you would like to test. The format would look something like this...

```json
{
    "id": [9083033499, "9083033499", -1, "", null, "$omit", "Hayden"],
    "name": ["Hayden", 12, "", null, "$omit"]
}
```

The first element of any options array must be a known valid input. This is to ensure that the program can have a known valid request that it can compare a potentially invalid request to. 

You may also notice the the strings that start with `'$'`. These are special options which perform some other functionality. The `"$omit"` special option will send the request through without that field. In this case: the body would have just been...

```json
{
    "name": "Hayden"
}
```

...as the id was ommited.

## params.json

```json
{
    "path": "",
    "query": ""
}
```

## headers.json

This is a static file to specify the headers of your function. The are no combinations and this json is passed directly as your headers. An example of this file includes...

```json
{
    "Content-Type": "application/json",
    "Accept": "application/json"
}
```

This file is not required and if it is not passed, the above file is used as the default.

## endpoints.json

This is a **required** json file to specify the endpoints that you will be hitting.

```json
{
    "legacy": "https://www.google.legacy.com",
    "migrated": "https://www.google.com"
}
```

## custom.json

This file is for specifying custom special options in your project. This is for the scenario where the two endpoints accept slightly different data. An example is that yhe two endpoints accept different date formats "MM-DD-YYYY" and "MM/DD/YYYY". This allows you to specify one of these formats for legacy and one for migrated. For example:

```json
{
    "$date": ["12-21-2002", "12/21/2002"]
}
```

Legacy will always take the first element and migrated will always take the second. Now if you make this call in your <u>body.json</u> file.

```json
{
    "date_of_birth": ["$date", "number"]
}
```

legacy will always take `"12-21-2002"` and migrated will always take `"12/21/2002"`, allowing always valid access on the first element on the combination array. 

You must always define these custom special options with a `"$"`. 