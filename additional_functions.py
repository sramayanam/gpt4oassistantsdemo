import json
import requests
import time
from openai import AzureOpenAI
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup
import re
import os

azure_endpoint = os.getenv("AZURE_ENDPOINT")
api_version = os.getenv("API_VERSION")
aoai_api_key =  os.getenv("AOAI_API_KEY")
bing_search_subscription_key = os.getenv("BING_SEARCH_SUBSCRIPTION_KEY")
bing_search_url = os.getenv("BING_SEARCH_URL")
deployment_name = os.getenv("DEPLOYMENT_NAME")
AZURE_MAPS_SUBSCRIPTION_KEY = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY")
TOMORROWIO_API_KEY = os.getenv("TOMORROWIO_API_KEY")
bing_key =  os.getenv("BING_KEY")
bing_endpoint = os.getenv("BING_ENDPOINT")

def get_topevents(query) -> list:
    headers = {"Ocp-Apim-Subscription-Key": bing_search_subscription_key}
    params = {"q": query, "textDecorations": False}
    response = requests.get(bing_search_url, headers=headers, params=params)
    response.raise_for_status()
    search_results = response.json()
    output = []

    for result in search_results["webPages"]["value"]:
         output.append({"title": result["name"], "link": result["url"], "snippet": result["snippet"]})
    return json.dumps(output)

def getLatLong(address):
    params = {
        'subscription-key': AZURE_MAPS_SUBSCRIPTION_KEY,
        'api-version': '1.0',
        'language': 'en-US',
        'query': address
    }

    response = requests.get('https://atlas.microsoft.com/search/address/json', params=params)
    data = response.json()

    try:
        lat = data['results'][0]['position']['lat']
        lon = data['results'][0]['position']['lon']
    except (IndexError, KeyError) as e:
        print(f'Error: {e}')
        return None

    return lat, lon

def weather (location,unit) -> list:
    lat, lon = getLatLong(location)
    url = "https://api.tomorrow.io/v4/weather/forecast?location=" + str(lat) + "," + str(lon) + "&apikey=" + TOMORROWIO_API_KEY
    payload = {}
    headers = {
    }
    response = requests.request("GET", url, headers=headers, data=payload)
    resp = json.loads(response.text)
    output = []
    output.append({"content": "The weather in " + location + " " + str(resp['timelines']["hourly"][0]["values"]["temperature"]) + " " +  unit })
    return json.dumps(output)

def poll_run_till_completion(
    client: AzureOpenAI,
    thread_id: str,
    run_id: str,
    available_functions: dict,
    verbose: bool,
    max_steps: int = 20,
    wait: int = 3,
) -> None:


    if (client is None and thread_id is None) or run_id is None:
        print("Client, Thread ID and Run ID are required.")
        return
    try:
        cnt = 0
        while cnt < max_steps:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            if verbose:
                print("Poll {}: {}".format(cnt, run.status))
            cnt += 1
            if run.status == "requires_action":
                tool_responses = []
                if (
                    run.required_action.type == "submit_tool_outputs"
                    and run.required_action.submit_tool_outputs.tool_calls is not None
                ):
                    tool_calls = run.required_action.submit_tool_outputs.tool_calls

                    for call in tool_calls:
                        if call.type == "function":
                            if call.function.name not in available_functions:
                                raise Exception("Function requested by the model does not exist")
                            function_to_call = available_functions[call.function.name]
                            tool_response = function_to_call(**json.loads(call.function.arguments))
                            print("################################################################")
                            print(call.id)
                            print('################################################################')
                            tool_responses.append({"tool_call_id": call.id, "output": tool_response})
                            print("################################################################")
                            print(tool_response)
                            print("################################################################")

                run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id, run_id=run.id, tool_outputs=tool_responses
                )
            if run.status == "failed":
                print("Run failed.")
                break
            if run.status == "completed":
                break
            time.sleep(wait)

    except Exception as e:
        print(e)


def create_message(
    client: AzureOpenAI,
    thread_id: str,
    role: str = "",
    content: str = "",
    file_ids: Optional[list] = None,
    metadata: Optional[dict] = None,
    message_id: Optional[str] = None,
) -> any:

    if metadata is None:
        metadata = {}
    if file_ids is None:
        file_ids = []

    if client is None:
        print("Client parameter is required.")
        return None

    if thread_id is None:
        print("Thread ID is required.")
        return None

    try:
        if message_id is not None:
            return client.beta.threads.messages.retrieve(thread_id=thread_id, message_id=message_id)

        if file_ids is not None and len(file_ids) > 0 and metadata is not None and len(metadata) > 0:
            return client.beta.threads.messages.create(
                thread_id=thread_id, role=role, content=content, file_ids=file_ids, metadata=metadata
            )

        if file_ids is not None and len(file_ids) > 0:
            return client.beta.threads.messages.create(
                thread_id=thread_id, role=role, content=content, file_ids=file_ids
            )

        if metadata is not None and len(metadata) > 0:
            return client.beta.threads.messages.create(
                thread_id=thread_id, role=role, content=content, metadata=metadata
            )

        return client.beta.threads.messages.create(thread_id=thread_id, role=role, content=content)

    except Exception as e:
        print(e)
        return None
    
def retrieve_and_print_messages(
    client: AzureOpenAI, thread_id: str, verbose: bool, out_dir: Optional[str] = None
) -> any:


    if client is None and thread_id is None:
        print("Client and Thread ID are required.")
        return None
    try:
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        display_role = {"user": "User query", "assistant": "Assistant response"}

        prev_role = None

        if verbose:
            print("\n\nCONVERSATION:")
        for md in reversed(messages.data):
            if prev_role == "assistant" and md.role == "user" and verbose:
                print("------ \n")

            for mc in md.content:
                # Check if valid text field is present in the mc object
                if mc.type == "text":
                    txt_val = mc.text.value
                # Check if valid image field is present in the mc object
                elif mc.type == "image_file":
                    image_data = client.files.content(mc.image_file.file_id)
                    if out_dir is not None:
                        out_dir_path = Path(out_dir)
                        if out_dir_path.exists():
                            image_path = out_dir_path / (mc.image_file.file_id + ".png")
                            with image_path.open("wb") as f:
                                f.write(image_data.read())

                if verbose:
                    if prev_role == md.role:
                        print(txt_val)
                    else:
                        print("{}:\n{}".format(display_role[md.role], txt_val))
            prev_role = md.role
        return messages
    except Exception as e:
        print(e)
        return None
    
def get_bing_search_url(search_term: str, freshness: Optional[str] = None) -> list:
    search_url = bing_endpoint
    headers = {"Ocp-Apim-Subscription-Key": bing_key}
    params = {"q": search_term, "textDecorations": True, "textFormat": "HTML"}
    if freshness:
        if freshness in ["Day", "Week", "Month"]:
            params["freshness"] = freshness
        else:
            raise ValueError("freshness must be 'Day', 'Week', or 'Month'")
    response = requests.get(search_url, headers=headers, params=params)

    response.raise_for_status()
    search_results = response.json()
    print(search_results)
    url_list = []

    if "webPages" in search_results:
        top_search_result = search_results["webPages"]["value"][0:1]
        for search_result in top_search_result:
            url_list.append(search_result["url"])
    print(url_list)
    return url_list


def replace_multiple_spaces(text: str) -> str:
    text = re.sub(" +", " ", text)
    return re.sub("\n+", "\n", text)


def load_url_content(url: str) -> str:
    print("in load url content")
    response = requests.get(url)

    soup = BeautifulSoup(response.text, "html.parser")
    content = soup.get_text()
    print(content)
    return replace_multiple_spaces(content)


def search_financedata(query: str, freshness: Optional[str] = None) -> str:
    url_list = get_bing_search_url(query, freshness)
    retval = []
    for url in url_list:
        retval.append(json.dumps({"url": url, "content": load_url_content(url)}))
    return ",".join(retval)
    print(ret_val)


