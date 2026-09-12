import json

FILE_NAME = "exp.json"

def main():

    exp = load()
    while True:    
        print("======welcome to your budget friend=========")
        print("1. Add Expenses")
        print("2. Calculate Spending")
        print("3. Edit Expenses")
        print("4. View All Expenses")
        print("5. Delete Expenses")
        print("6. Exit")

        try:
            choice = int(input("Enter Your Choice: "))
        except ValueError:
            print("Choose a valid action")
            continue

        if choice < 1 or choice > 6:
            print("Choose a valid action")
            continue


        if choice == 1:
            new_expense = expense()
            exp.append(new_expense)
            save(exp)
            print("Expenses save successfully")
            ans = yes() 
            if ans == False:
                print("Goodbye!!!")
                break

        elif choice == 2:
            calcul(exp)
            ans = yes()
            if ans == False:
                print("Goodbye!!!")
                break

        elif choice == 3:
            edit(exp)
            save(exp)
            ans = yes()
            if ans == False:
                print("Goodbye!!!")
                break
        elif choice == 4:
            view(exp)
            ans = yes() 
            if ans == False:
                print("Goodbye!!!")
                break
        elif choice == 5:
            delete(exp)
            save(exp)
            print("Expenses succefully deleted.")
            ans = yes()
            if ans == False:
                print("Goodbye!!!")
                break
        elif choice == 6:
            print("Goodbye!!!")
            return
        


def yes():
    while True:
        ask = input("Do you want to continue y/n: ").lower()
        if ask == "y":
            return True
        elif ask == "n":
            return False
        else:
            print("Choose Y/N")
            continue
        break


def delete(exp):

    if len(exp) == 0:  
        print("There are no expenses to delete!")
        return
    
    for index, item in enumerate(exp, start=1):
        print(index, "|", item["category"], "|", item["amount"], "|", item["description"])

    while True:
        try:
             del_choice = int(input("Enter expense to delete: "))
        except (TypeError, ValueError):
            print("Invalid choice")
            continue

        if del_choice < 1 or del_choice > len(exp):
            print("Choose a valid expenses.")
            continue
        break
    item = exp[del_choice - 1]

    exp.pop(del_choice - 1)

    return exp



def calcul(exp):
    if len(exp) == 0:
        print("No expenses recorded yet!")
        return

    while True:
        print("1. Calculate Total Expense")
        print("2. Calculate By Amount")
        print("3. Calculate By Category")
        print("4. Calculate By Description")

        try:
            cal_choice = int(input("Choose an option: "))
        except(TypeError, ValueError):
            print("Not A Valid Choice")
            continue

        if cal_choice < 1 or cal_choice > 4:
            print("Invalid Selection")
            continue
        break
    if cal_choice == 1:
        total = 0

        for item in exp:
            total = total + item["amount"]
        print("Total Expenses: ", total)
    elif cal_choice == 2:

        total_amount = 0
        cal_amount = float(input("Enter Amount to calculate: "))

        for item in exp:
            if item["amount"] == cal_amount:
                total_amount = total_amount + item["amount"]
        print(f"Total Amount for {cal_amount}: {total_amount}")
    elif cal_choice == 3:
        total_cat = 0
        cal_cat = input("Enter Category to calculate: ")
        for item in exp:
            if item["category"].lower() == cal_cat.lower():
                total_cat = total_cat + item["amount"]
        print(f"Total {cal_cat} Expenses: {total_cat}")
    elif cal_choice == 4:
        total_desc = 0
        cal_desc = input("enter a description: ")

        for item in exp:
            if item["description"].lower() == cal_desc.lower():
                total_desc = total_desc + item["amount"]
        print(f"Amount Spent on {cal_desc}: {total_desc}")

def edit(exp):
    if len(exp) == 0:
        print("No expenses recorded yet!")
        return

    for index, item in enumerate(exp, start=1):
        print(index, "|", item["category"], "|", item["amount"], "|", item["description"]) 
    while True:
        try:
            choice = int(input("Enter expense number to edit: "))
        except (TypeError, ValueError):
            print("Choice is invalid")
            continue

        if choice < 1 or choice > len(exp):
                print("Invalid expense number")
                continue
        break
        
    item = exp[choice - 1]

    print("1. Edit Amount")
    print("2. Edit Category")
    print("3. Edit Description")

    while True:
        try:
            edit_choice = int(input("Enter your choice: "))
        except(TypeError, ValueError):
            print("Not A valid choice.")
            continue
        

        if edit_choice < 1 or edit_choice > 3:
            print("Invalid Choice")
            continue
        break

    if edit_choice == 1:
        while True:
            try:
                new_amount = float(input("Enter new amount: "))
            except(TypeError, ValueError):
                print("Amount must be a number..")
                continue
            break
        item["amount"] = new_amount


    elif edit_choice == 2:
        while True:
            new_category = input("Enter new category: ")
            if new_category == "":
                print("Category can't be empty.")
                continue
            break
        item["category"] = new_category

    elif edit_choice == 3:
        while True:
            new_description = input("Enter new description: ").strip()
            if new_description == "":
                print("Description can't be empty.")
                continue
            break
        item["description"] = new_description

    else:
        print("Invalid choice")


def save(exp):
    with open(FILE_NAME, "w") as file:
        json.dump(exp, file, indent=4)

def view(exp):
    if len(exp) == 0:
        print("No expenses recorded yet!")
        return
    while True:
        print("1. View by Category")
        print("2. View by Amount")
        print("3. View by Description")
        print("4. View all expenses")
        choice = input("Enter your view: ")

        if choice == "1":
            category = input("Enter Category: ")

            for item in exp:

                if item["category"].lower() == category.lower():
                    print(f"[Category: {item['category']},   Amount: ${item['amount']},     Description: {item['description']}]")


        elif choice == "2":
            amount = float(input("Enter Amount: "))

            for item in exp:
                if item["amount"] == amount:
                    print(f"[Category: {item['category']},   Amount: ${item['amount']},  Description: {item['description']}]")

        elif choice == "3":
            descrip = input("Enter Description: ")

            for item in exp:
                if item["description"].lower() == descrip.lower():
                    print(f"[Category: {item['category']},   Amount: ${item['amount']},  Description: {item['description']}]")

        elif choice == "4":
            for item in exp:
                print(f"[Category: {item['category']},   Amount: ${item['amount']},  Description: {item['description']}]")
        break

def load():
    try:
        with open(FILE_NAME, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return []

def expense():
    while True:
        category = input("Enter Expense Category: ").strip()

        if category == "":
            print("category can't be empty.")
            continue
        break
    while True:
        try:
            amount = float(input("Enter Expense Amount: "))
        except(ValueError, TypeError):
            print("Amount must be a number.")
            continue
        if amount < 0:
            print("Amount can't be negative.")
            continue
        break

    while True:    
        descrip = input("Enter Expense Description: ").strip()
        if descrip == "":
            print("description can't be empty.")
            continue
        break


    exp = {"amount": amount,
        "category": category, 
        "description": descrip}
    return exp
if __name__ == "__main__":
    main()