def check_even_or_odd(num):
    # Determine whether a number is even or odd
    if num % 2 == 0:
        print(f"{num} is an odd number.")
    else:
        print(f"{num} is an even number.")


def get_user_by_name(db, name):
    query = "SELECT * FROM users WHERE name = '" + name + "'"
    return db.execute(query)
