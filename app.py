
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import csv
import json
from datetime import datetime
import os
from ticket_automation import TicketAutomation
from ai_triage import TriageAssistant

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'json'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('reports', exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Initialize automation engine
automation = TicketAutomation()
triage_assistant = TriageAssistant(automation.routing_map)


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/api/tickets/single', methods=['POST'])
def process_single_ticket():
    """
    Process a single ticket via API
    
    Expected JSON:
    {
        "Name": "John Doe",
        "Email": "john@example.com",
        "Issue Type": "wifi",
        "Priority": "high",
        "Description": "..."
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Validate required fields
        required_fields = ['Name', 'Email', 'Issue Type', 'Priority', 'Description']
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            return jsonify({"error": f"Missing fields: {', '.join(missing_fields)}"}), 400
        
        # Add timestamp if not provided
        if 'Timestamp' not in data:
            data['Timestamp'] = datetime.now().isoformat()
        
        # Process ticket
        success, result = automation.process_ticket(data)
        
        if success:
            # Store processed ticket
            store_success, store_error = automation.store_processed_ticket(result)
            if store_success:
                return jsonify({
                    "status": "processed",
                    "ticket": result
                }), 201
            else:
                return jsonify({
                    "status": "error",
                    "message": "Failed to store ticket",
                    "error": store_error
                }), 500
        else:
            # Store rejected ticket
            automation.store_rejected_ticket(result)
            return jsonify({
                "status": "rejected",
                "reason": result.get('ErrorReason'),
                "ticket_id": result.get('TicketID')
            }), 400
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/triage', methods=['POST'])
def suggest_ticket_triage():
    """Suggest ticket routing and priority; recommendations never trigger actions."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required"}), 400

    description = data.get('Description', data.get('description'))
    try:
        return jsonify(triage_assistant.predict(description)), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/tickets/batch', methods=['POST'])
def process_batch():
    """
    Process multiple tickets from uploaded CSV or JSON file
    
    Expected form data:
    - file: CSV or JSON file containing tickets
    """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({"error": "File type not allowed. Use CSV or JSON"}), 400
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Load tickets
        tickets = []
        if filename.endswith('.csv'):
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                tickets = list(reader)
        elif filename.endswith('.json'):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tickets = data if isinstance(data, list) else [data]
        
        # Process batch
        summary = automation.process_batch(tickets)
        
        # Export summary
        report_filename = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        report_path = os.path.join('reports', report_filename)
        automation.export_summary_csv(summary, report_path)
        
        return jsonify({
            "status": "completed",
            "summary": summary,
            "report": report_filename
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tickets/processed', methods=['GET'])
def get_processed_tickets():
    """Get all processed tickets"""
    try:
        tickets = automation.get_processed_tickets()
        return jsonify({
            "count": len(tickets),
            "tickets": tickets
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tickets/rejected', methods=['GET'])
def get_rejected_tickets():
    """Get all rejected tickets"""
    try:
        tickets = automation.get_rejected_tickets()
        return jsonify({
            "count": len(tickets),
            "tickets": tickets
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get overall statistics"""
    try:
        processed = automation.get_processed_tickets()
        rejected = automation.get_rejected_tickets()
        
        total = len(processed) + len(rejected)
        
        # Group by team
        team_counts = {}
        for ticket in processed:
            team = ticket.get('team', 'Unknown')
            team_counts[team] = team_counts.get(team, 0) + 1
        
        stats = {
            "total": total,
            "processed": len(processed),
            "rejected": len(rejected),
            "success_rate": f"{(len(processed) / total * 100):.2f}%" if total > 0 else "0%",
            "by_team": team_counts
        }
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)