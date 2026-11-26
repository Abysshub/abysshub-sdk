# vulture's findings when the dead-code check began, which it no longer reports. A name
# leaves when its last finding is gone (tests/test_package.py checks that each still is).
exc_type  # unused variable (src/abysshub/_async_client.py:147, src/abysshub/_client.py:384)
exc  # unused variable (src/abysshub/_async_client.py:148, src/abysshub/_client.py:385)
tb  # unused variable (src/abysshub/_async_client.py:149, src/abysshub/_client.py:386)
format  # unused variable (tests/fake_server.py:53)
