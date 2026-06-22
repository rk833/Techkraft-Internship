# This is a simple calculator program that demonstrates basic arithmetic operations.

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        return "Error: Cannot divide by zero"
    return a / b


def get_numbers():
    a = float(input("Enter first number: "))
    b = float(input("Enter second number: "))
    return a, b

# menu.py
def show_menu():
    print("\n--- Calculator ---")
    print("1. Add")
    print("2. Subtract")
    print("3. Multiply")
    print("4. Divide")
    print("5. Exit")

# main.py
def main():
    while True:
        show_menu()
        choice = input("Choose option (1-5): ")

        if choice == "5":
            print("Goodbye!")
            break

        if choice in ["1", "2", "3", "4"]:
            a, b = get_numbers()

            if choice == "1":
                print("Result:", add(a, b))
            elif choice == "2":
                print("Result:", subtract(a, b))
            elif choice == "3":
                print("Result:", multiply(a, b))
            elif choice == "4":
                print("Result:", divide(a, b))
        else:
            print("Invalid choice. Try again.")


if __name__ == "__main__":
    main()