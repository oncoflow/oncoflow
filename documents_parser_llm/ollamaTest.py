from ollama import Client
client = Client(host='http://10.8.0.2:11434', request_timeout=1000)
response = client.chat(model='llama3.1', messages=[
  {
    'role': 'user',
    'content': 'Why is the sky blue?',
  },
])

print(response)