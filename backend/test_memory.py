from app.memory.memory import memory

memory.add_message(
    "user1",
    "user",
    "Hello"
)

memory.add_message(
    "user1",
    "assistant",
    "Hi!"
)

print(memory.get_history("user1"))
