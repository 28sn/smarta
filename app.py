from flask import Flask, render_template, jsonify, request, redirect, url_for, send_file
from datetime import datetime
import requests
import os
import scan  # ملف خاص بعملية المسح بالكاميرا
from scan import get_product_info
from io import BytesIO
import qrcode

app = Flask(__name__)

PRODUCT_FILE = "product_info.txt"
RECIPE_FILE = "recipes.txt"
SHOPPING_FILE = "shopping_cart.txt"

# دوال المساعدة
def read_products():
    if not os.path.exists(PRODUCT_FILE):
        return []
    with open(PRODUCT_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
    blocks = content.split("==================================================")
    products = []
    for block in blocks:
        lines = block.strip().splitlines()
        data = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key == "product name":
                    data["name"] = val
                elif key == "brand":
                    data["brand"] = val
                elif key == "ingredients":
                    data["ingredients"] = val
                elif key == "energy":
                    data["energy"] = val.replace("kcal", "").strip()
                elif key == "expiration date":
                    data["expires"] = val
                elif key == "barcode":
                    data["barcode"] = val
        if data:
            products.append(data)
    return products

def read_cart():
    if not os.path.exists(SHOPPING_FILE):
        return []
    with open(SHOPPING_FILE, "r") as f:
        lines = f.read().strip().splitlines()
    cart = {}
    for line in lines:
        item = line.strip().lower()
        if item:
            cart[item] = cart.get(item, 0) + 1
    return [{"name": name, "quantity": qty} for name, qty in cart.items()]

def add_to_cart(items):
    with open(SHOPPING_FILE, "a") as f:
        for item in items:
            f.write(item.strip().lower() + "\n")

def read_recipes():
    if not os.path.exists(RECIPE_FILE):
        return []
    with open(RECIPE_FILE, "r") as f:
        lines = f.read().strip().splitlines()
    recipes = []
    current = {}
    for line in lines:
        if line.startswith("name:"):
            if current:
                recipes.append(current)
            current = {"name": line.replace("name:", "").strip()}
        elif line.startswith("ingredients:"):
            ing = line.replace("ingredients:", "").strip()
            current["ingredients"] = [i.strip().lower() for i in ing.split(",")]
    if current:
        recipes.append(current)
    return recipes

# المسارات
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/alerts")
def alerts():
    today = datetime.today()
    products = read_products()
    alerts = {"expired": [], "ok": [], "soon": []}
    for product in products:
        if "expires" in product and product["expires"]:
            try:
                exp = datetime.strptime(product["expires"], "%Y-%m-%d")
                diff = (exp - today).days
                if diff < 0:
                    product["status"] = "expired"
                    alerts["expired"].append(product)
                elif diff <= 30:
                    product["status"] = "soon"
                    alerts["soon"].append(product)
                else:
                    product["status"] = "ok"
                    alerts["ok"].append(product)
            except:
                continue
    return render_template("alerts.html", alerts=alerts)

@app.route("/inventory")
def inventory():
    return render_template("inventory.html", products=read_products())

@app.route("/recipes")
def recipes():
    return render_template("recipes.html")

@app.route("/shopping")
def shopping():
    return render_template("shopping.html")

@app.route("/api/products")
def get_all_products():
    return jsonify(read_products())

@app.route("/api/shopping")
def get_shopping_cart():
    return jsonify(read_cart())

@app.route("/api/shopping/add", methods=["POST"])
def add_shopping_items():
    data = request.json
    items = data.get("items", [])
    add_to_cart(items)
    return jsonify({"status": "success", "added": items})

@app.route("/api/shopping/remove", methods=["POST"])
def remove_item():
    data = request.json
    item_to_remove = data.get("item", "").strip().lower()
    if not os.path.exists(SHOPPING_FILE):
        return jsonify({"status": "error", "message": "file not found"})
    with open(SHOPPING_FILE, "r") as f:
        items = f.read().splitlines()
    removed = False
    new_items = []
    for i in items:
        if i.strip().lower() == item_to_remove and not removed:
            removed = True
            continue
        new_items.append(i)
    with open(SHOPPING_FILE, "w") as f:
        f.write("\n".join(new_items) + "\n")
    return jsonify({"status": "removed" if removed else "not found"})

@app.route("/api/qr_shopping")
def generate_shopping_qr():
    cart = read_cart()
    if not cart:
        return jsonify({"message": "🧺 السلة فارغة"})
    content = "\n".join([f"- {item['name']} × {item['quantity']}" for item in cart])
    qr = qrcode.make(content)
    img_io = BytesIO()
    qr.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

@app.route("/api/recipes")
def get_local_recipes():
    products = read_products()
    all_ingredients = []
    for p in products:
        if "ingredients" in p and p["ingredients"].lower() != "not available":
            all_ingredients += [i.strip().lower() for i in p["ingredients"].split(",")]
    available = set(all_ingredients)
    suggestions = []
    for recipe in read_recipes():
        needed = set(recipe["ingredients"])
        missing = list(needed - available)
        match_level = len(needed) - len(missing)
        suggestions.append({
            "name": recipe["name"],
            "available": list(needed & available),
            "missing": missing,
            "match_percent": int((match_level / len(needed)) * 100)
        })
    suggestions.sort(key=lambda x: -x["match_percent"])
    return jsonify(suggestions)

@app.route("/api/recipes/online")
def get_online_recipes():
    products = read_products()
    all_ingredients = []
    for p in products:
        if "ingredients" in p and p["ingredients"].lower() != "not available":
            all_ingredients += [i.strip().lower() for i in p["ingredients"].split(",")]
    available = set(all_ingredients)
    category_url = "https://www.themealdb.com/api/json/v1/1/filter.php?c=Beef"
    response = requests.get(category_url)
    if response.status_code != 200:
        return jsonify([]) 
    meals = response.json().get("meals", [])[:10]
    suggestions = []
    for meal in meals:
        detail_res = requests.get(f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal['idMeal']}")
        meal_data = detail_res.json().get("meals", [])[0]
        ingredients = []
        for i in range(1, 21):
            ing = meal_data.get(f"strIngredient{i}")
            if ing and ing.strip():
                ingredients.append(ing.strip().lower())
        match = list(set(ingredients) & available)
        missing = list(set(ingredients) - available)
        if match:
            suggestions.append({
                "name": meal_data["strMeal"],
                "thumbnail": meal_data["strMealThumb"],
                "instructions": meal_data["strInstructions"],
                "source": meal_data.get("strSource") or f"https://www.themealdb.com/meal/{meal['idMeal']}",
                "available": match,
                "missing": missing
            })
    return jsonify(suggestions)

@app.route("/add_product", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        product_name = request.form["productName"]
        brand = request.form["brand"]
        ingredients = request.form["ingredients"]
        energy = request.form["energy"]
        expiration_date = request.form["expirationDate"]
        barcode = request.form["barcode"]

        if not expiration_date:
            expiration_date = "غير متوفر"

        with open(PRODUCT_FILE, "a", encoding="utf-8") as file:
            file.write(f"Product Information:\n")
            file.write(f"Product Name: {product_name}\n")
            file.write(f"Brand: {brand}\n")
            file.write(f"Ingredients: {ingredients}\n")
            file.write(f"Energy: {energy}\n")
            file.write(f"Expiration Date: {expiration_date}\n")
            file.write(f"Barcode: {barcode}\n")
            file.write("="*50 + "\n")

        return redirect(url_for("inventory"))
    return render_template("add_product.html")

@app.route("/start_scan")
def start_scan():
    return scan.start_scan()

@app.route("/enter_expiration_date")
def enter_expiration_date():
    barcode = request.args.get('barcode')
    return render_template("enter_expiration_date.html", barcode=barcode)

@app.route("/save_product_expiration", methods=["POST"])
def save_product_expiration():
    barcode = request.form["barcode"]
    expiration_date = request.form["expirationDate"]
    if not expiration_date:
        return "تاريخ الانتهاء مطلوب ولا يمكن أن يكون فارغًا."
    product_info = get_product_info(barcode)
    if product_info:
        product_info["expiration_date"] = expiration_date
        with open(PRODUCT_FILE, "a", encoding="utf-8") as f:
            f.write(f"Product Information:\n")
            f.write(f"Product Name: {product_info.get('product_name', 'Not available')}\n")
            f.write(f"Brand: {product_info.get('brands', 'Not available')}\n")
            f.write(f"Ingredients: {product_info.get('ingredients_text', 'Not available')}\n")
            f.write(f"Energy: {product_info.get('nutriments', {}).get('energy-kcal', 'Not available')} kcal\n")
            f.write(f"Expiration Date: {expiration_date}\n")
            f.write(f"Barcode: {barcode}\n")
            f.write("="*50 + "\n")
        return redirect(url_for("inventory"))
    else:
        return render_template("product_not_found.html", barcode=barcode, message="المنتج غير موجود أو لم يتم التعرف عليه.")

if __name__ == "__main__":
    app.run(debug=True)
