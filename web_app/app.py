from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return "<p1> CitationMap </p1>"

if __name__ == '__main__':
    app.run()
