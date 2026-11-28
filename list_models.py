# Print every model your key can call that supports generate_content.
from ask import client
for m in client.models.list():
    if "generateContent" in (m.supported_actions or []):
        print(m.name)