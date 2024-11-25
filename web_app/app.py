from flask import Flask, request, jsonify

app = Flask(__name__)

def run_program(input_string, options):
    """
    Example function that processes the input string and options.
    Replace this with your actual program logic.
    """
    result = f"Processed '{input_string}' with options: {', '.join(options)}"
    return result

@app.route('/run_program', methods=['POST'])
def handle_request():
    data = request.get_json()
    input_string = data.get('input_string', '')
    options = data.get('options', [])

    if not input_string:
        return jsonify({'error': 'Input string is required'}), 400

    try:
        # Run the program with the provided input and options
        result = run_program(input_string, options)
        return jsonify({'result': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
