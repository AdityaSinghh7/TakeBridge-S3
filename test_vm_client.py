from server.api.controller_client import VMControllerClient

client = VMControllerClient(base_url="http://127.0.0.1:5000")
print(client.get_platform())
print(client.screen_size())
shot = client.capture_screenshot()
with open("/Users/Shared/TakeBridge/test-from-main.png", "wb") as f:
    f.write(shot)

