import json
from datetime import datetime

FILENAME = "todo.json"

def write(todo):
    with open(FILENAME, "w") as file:
            json.dump(todo, file, indent=4)


def load():

    try:
        with open(FILENAME, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return []

def add():

    status = "Pending"
    while True:
        title = input("Enter Task Title: ")

        if title == "":
             print("Title Can't Be Empty!!!")
             continue
        else:
             break
    while True:
        desc = input("Enter Task Description: ")
        if desc == "":
            print("Description Can't Be Empty!!!")
            continue
        else:
            break
    while True:
        prio = input("Enter Task Priority: ")
        if prio == "":
            print("Priority Cannot Be Empty!!!")
            continue
        else:
            break
    while True:
        due = input("Enter Task Due-Date : ")

        try:
            datetime.strptime(due, "%Y-%m-%d")
        except(ValueError, TypeError):
            print("Enter A Valid Date!!!")
            continue
        break
    task = {
        "Title": title,
        "Description": desc,
        "Priority": prio,
        "Due-Date": due,
        "Created At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Status": status
    }

    return task


def view():
    while True:
        print("[1]. View By Title")
        print("[2]. View By Due-Date")
        print("[3]. View By Status")
        

def main():
    tasks =[]


    while True:
        print("1. Add Task")
        print("2. View Tasks")
        print("3. Complete Task")
        print("4. Edit Task")
        print("5. Delete Task")
        print("6. Exit")


        try:
            choice = int(input("Enter an option: "))
        except(ValueError, TypeError):
            print("Enter A valid Option!!!")
            continue

        if choice < 1 or choice > 6:
            print("Enter A valid Opt")
            continue


        if choice == 1:
            task = add()
            tasks.append(task)
            write(tasks)
        


if __name__ == "__main__":
    main()