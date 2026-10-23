import pickle

FILENAME = "flights.dat"


def add_flight():
    flight_no = input("Enter flight number: ").strip().upper()

    # Check for a duplicate flight number (file may not exist yet)
    try:
        with open(FILENAME, "rb") as file:
            while True:
                try:
                    record = pickle.load(file)
                    if record["flight_no"].upper() == flight_no:
                        print("A record with this flight number already exists.")
                        return
                except EOFError:
                    break
    except FileNotFoundError:
        pass

    airline = input("Enter airline name: ").strip()
    destination = input("Enter destination: ").strip()

    try:
        passengers = int(input("Enter number of passengers: "))
        if passengers < 0:
            print("Passenger count cannot be negative.")
            return
    except ValueError:
        print("Please enter the passenger count as a whole number.")
        return

    record = {
        "flight_no": flight_no,
        "airline": airline,
        "destination": destination,
        "passengers": passengers
    }

    with open(FILENAME, "ab") as file:
        pickle.dump(record, file)
    print("Flight record saved successfully.")


def display_flights():
    count = 0
    try:
        with open(FILENAME, "rb") as file:
            while True:
                try:
                    record = pickle.load(file)
                    if count == 0:
                        print("\n--- ALL FLIGHT RECORDS ---")
                    count += 1
                    print("Flight Number :", record["flight_no"])
                    print("Airline       :", record["airline"])
                    print("Destination   :", record["destination"])
                    print("Passengers    :", record["passengers"])
                    print("-" * 30)
                except EOFError:
                    break
    except FileNotFoundError:
        pass

    if count == 0:
        print("No flight records found.")


def search_flight():
    flight_no = input("Enter flight number to search: ").strip().upper()
    try:
        with open(FILENAME, "rb") as file:
            while True:
                try:
                    record = pickle.load(file)
                    if record["flight_no"].upper() == flight_no:
                        print("\n--- FLIGHT FOUND ---")
                        print("Flight Number :", record["flight_no"])
                        print("Airline       :", record["airline"])
                        print("Destination   :", record["destination"])
                        print("Passengers    :", record["passengers"])
                        return
                except EOFError:
                    break
    except FileNotFoundError:
        print("No flight records found.")
        return

    print("Flight not found.")


def main():
    while True:
        print("\n===== AIRPORT MANAGEMENT SYSTEM =====")
        print("1. Add Flight Record")
        print("2. Display All Flight Records")
        print("3. Search for a Flight")
        print("4. Exit")
        choice = input("Enter your choice: ").strip()

        if choice == "1":
            add_flight()
        elif choice == "2":
            display_flights()
        elif choice == "3":
            search_flight()
        elif choice == "4":
            print("Thank you for using Airport Management System.")
            break
        else:
            print("Invalid choice. Please choose 1, 2, 3, or 4.")


if __name__ == "__main__":
    main()
