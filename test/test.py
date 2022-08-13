from pyautogui import press,typewrite
from time import sleep
from datetime import datetime,timedelta

#write the sequence of commands you'd like to execute in the test.txt file

wait = 2
commands = []
with open("test.txt", "r") as cmd_file:
    commands = [l.rstrip("\n") for l in cmd_file.readlines()]

print("Place your cursor in the chatbox.")
for i in range(5,0,-1):
    print(i)
    sleep(1)

for command in commands:
    typewrite(command)
    press("enter")
    sleep(wait)

one_min = datetime.now() + timedelta(minutes=1)
typewrite(f"/setdailyreminder {one_min.hour}:{one_min.minute:02d}")
press("enter")
for i in range(60 - one_min.second + 5,0,-1):
    print(i)
    sleep(1)
typewrite(f"/stopdailyreminder {one_min.hour}:{one_min.minute:02d}")
press("enter")