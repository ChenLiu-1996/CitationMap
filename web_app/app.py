from flask import Flask, render_template, request, send_file, redirect, url_for
from citation_map import generate_citation_map
import os

app = Flask(__name__)

OUTPUT_HTML = "citation_map.html"
OUTPUT_CSV = "citation_info.csv"


@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')

@app.route("/run/", methods=['POST'])
def run_citationmap():
    # Retrieve the 'scholar_id' from user input.
    scholar_id = request.form.get('scholar_id')

    if not scholar_id:
        return "Error: Please provide a Google Scholar ID", 400  # Handle missing scholar ID

    # Call the citation map generation function.
    try:
        generate_citation_map(scholar_id=scholar_id)
    except Exception as e:
        return f"Error generating citation map: {str(e)}", 500

    # Redirect to a page where users can download the outputs
    return redirect(url_for('downloads'))

@app.route('/downloads/', methods=['GET'])
def downloads():
    return render_template('downloads.html',
                           html_file=OUTPUT_HTML,
                           csv_file=OUTPUT_CSV)

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    # Serve the requested file dynamically
    file_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return "Error: File not found.", 404


if __name__ == '__main__':
    app.run()