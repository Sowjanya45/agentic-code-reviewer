def get_discounted_price(price, discount_percent):
    # Apply a percentage discount to a price
    discount = price * discount_percent / 100
    return price + discount  # BUG: should subtract the discount, not add it


def load_user_settings(path):
    f = open(path)
    return json.loads(f.read())  # file handle is never closed, and json is never imported


def is_admin(user):
    if user.role = "admin":
        return True
    return False
