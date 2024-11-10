import azure.functions as func
import json
from openai import AzureOpenAI
from additional_functions import weather, get_topevents, poll_run_till_completion, create_message, retrieve_and_print_messages, search_financedata
import os

app = func.FunctionApp()
@app.function_name(name='ask')
@app.route(route='ask', auth_level='anonymous', methods=['POST'])

def main(req):
    azure_endpoint = os.getenv("AZURE_ENDPOINT")
    api_version = os.getenv("API_VERSION")
    aoai_api_key =  os.getenv("AOAI_API_KEY") 
    prompt = req.params.get('prompt') 
    print("Printing the Prompt:::::",prompt)
    if not prompt: 
        try: 
            req_body = req.get_json() 
        except ValueError: 
            raise RuntimeError("prompt data must be set in POST.") 
        else: 
            prompt = req_body.get('prompt') 
            if not prompt:
                raise RuntimeError("prompt data must be set in POST.")

    name = os.getenv("ASSISTANT_NAME")
    
    instructions = """You are a helpful assistant who helps me dress appropriately for the weather in a given city. Provide me a fashionable outfit. Please use multiple tools at your disposal. Adhere to the following steps.

            - First understand the provided input in the context of the country, State and the city. This is a required step to call the tools. Some Examples are "Frisco, Texas", "New York, New York", "London, England", "Madrid Spain".

            - You have access to query the web using Bing Search to fetch the latest list of events. you also have access to get real time temperature from a weather tool. 

            - Once you are at this step provide a consolidated reply to the user with the latest events happening in the city and the weather forecast. 

        """
    message = {"role": "user", "content": prompt}


    tools = [
    {
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "description": "Get the weather for a city in celsius",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "The city and state, e.g. San Francisco, CA"
                                },
                                "unit": {
                                    "type": "string",
                                    "enum": ["celsius", "fahrenheit"]
                                }
                            },
                            "required": ["location"]
                        }
                    }},
                {
                    "type": "function",
                    "function": {
                        "name": "search_financedata",
                        "description": "Get the finance data from web as needed if the user is asking about specific financial information.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The finance metrics that need to be searched"
                                },
                                "freshness": {
                                    "type": "string",
                                    "description": "The freshness of the data. e.g. today, yesterday, last week, last month, last year"
                                }
                            },
                            "required": ["query"]
                        }
                    }},
            {   
                    "type": "function",
                    "function": {                   
                        "name": "get_topevents",
                        "description": "Search and Retrieve latest events happening in the city. Response must be consise and relevant.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The query string to search the events. e.g. Top events in Spain Madrid today.",
                                }
                            },
                            "required": ["query"]
                        }
                    }
            } 
    ]

    available_functions = {"weather": weather,"get_topevents": get_topevents,"search_financedata": search_financedata}
    verbose_output = False
    client = AzureOpenAI(api_key=aoai_api_key, api_version=api_version, azure_endpoint=azure_endpoint)
    assistants = []
    for assistant in json.loads(client.beta.assistants.list().model_dump_json())['data']:
        if assistant['name'] == name:
            assistants.append(assistant['id'])
    a = client.beta.assistants.retrieve(assistants[0])
    thread = client.beta.threads.create()
    create_message(client, thread.id, message["role"], message["content"])
    run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=a.id, instructions=instructions)
    poll_run_till_completion(
        client=client, thread_id=thread.id, run_id=run.id, available_functions=available_functions, verbose=verbose_output
    )
    messages = retrieve_and_print_messages(client=client, thread_id=thread.id, verbose=verbose_output)
    output = json.loads(messages.model_dump_json())['data'][0]['content'][0]['text']['value']
    #print(output)
    output_json = json.dumps({"data": output})
    print(output_json)
    return func.HttpResponse(output_json,mimetype="application/json") 

