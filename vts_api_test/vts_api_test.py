import pyvts
import asyncio

async def main():
    plugin_name = "Expression Controller"
    developer = "Rotten Work"
    authentication_token_path = "./token.txt"

    plugin_info = {
        "plugin_name": plugin_name,
        "developer": developer,
        "authentication_token_path": authentication_token_path
    }

    myvts = pyvts.vts(plugin_info=plugin_info)
    try:
        await myvts.connect()
    except:
        print("Connect failed")
        
    try:
        await myvts.read_token()
        print("Token file found.")
    except FileNotFoundError:
        print("No token file found! Do authentication!")
        await myvts.request_authenticate_token()
        await myvts.write_token()
    
    await myvts.request_authenticate()

    expression_file = "test.exp3.json"
    while True:
        user_input = input("Press 1 to activate, 2 to deactivate, 0 to quit:\n")
        if user_input == '1':
            active = True
        elif user_input == '2':
            active = False
        elif user_input == '0':
            break
        else:
            continue
    
        expression_request_data = {
            "expressionFile": expression_file,
            "active": active
        }

        expression_request_msg = myvts.vts_request.BaseRequest(
            "ExpressionActivationRequest",
            expression_request_data,
            "ExpressionActivationRequestID"
        )

        expression_response = await myvts.request(expression_request_msg)

        # https://datagy.io/python-check-if-dictionary-empty/
        # The expression_response[‘data’] dict should be empty if the request is successful.
        assert not bool(expression_response['data'])
        
    await myvts.close()

async def connect_auth(myvts):

    await myvts.connect()

    try:
        await myvts.read_token()
        print("Token file found.")
    except FileNotFoundError:
        print("No token file found! Do authentication!")
        await myvts.request_authenticate_token()
        await myvts.write_token()
    
    await myvts.request_authenticate()

async def activate(myvts):
    expression_file = "test.exp3.json"
    active = True
    expression_request_data = {
        "expressionFile": expression_file,
        "active": active
    }

    expression_request_msg = myvts.vts_request.BaseRequest(
        "ExpressionActivationRequest",
        expression_request_data,
        "ExpressionActivationRequestID"
    )

    expression_response = await myvts.request(expression_request_msg)


    # The expression_response[‘data’] dict should be empty if the request is successful.
    assert not bool(expression_response['data'])

async def deactivate(myvts):
    expression_file = "test.exp3.json"
    active = False
    expression_request_data = {
        "expressionFile": expression_file,
        "active": active
    }

    expression_request_msg = myvts.vts_request.BaseRequest(
        "ExpressionActivationRequest",
        expression_request_data,
        "ExpressionActivationRequestID"
    )

    expression_response = await myvts.request(expression_request_msg)

    # The expression_response[‘data’] dict should be empty if the request is successful.
    assert not bool(expression_response['data'])

async def close(myvts):
    await myvts.close()


if __name__ == "__main__":
    asyncio.run(main())

    plugin_name = "expression controller"
    developer = "Rotten Work"
    authentication_token_path = "./token.txt"

    plugin_info = {
        "plugin_name": plugin_name,
        "developer": developer,
        "authentication_token_path": authentication_token_path
    }

    myvts = pyvts.vts(plugin_info=plugin_info)

    # Doesn't work, because loop is automatically close after every run
    # asyncio.run(connect_auth(myvts))
    # asyncio.run(activate(myvts))
    # # asyncio.run(deactive(myvts))
    # asyncio.run(close(myvts))

    # create and access a new asyncio event loop
    loop = asyncio.new_event_loop()

    # task = loop.create_task(connect_auth(myvts))
    # https://tutorialedge.net/python/concurrency/asyncio-event-loops-tutorial/
    task = loop.run_until_complete(connect_auth(myvts))
    task = loop.run_until_complete(activate(myvts))
    task = loop.run_until_complete(deactivate(myvts))
    task = loop.run_until_complete(close(myvts))

    loop.close()

