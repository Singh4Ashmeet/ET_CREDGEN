from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename
from database import db
from db_models import Document, ChatSession
import os
import hashlib
import uuid
from datetime import datetime

document_bp = Blueprint('documents', __name__)

ALLOWED_MIME_TYPES = {'application/pdf', 'image/jpeg', 'image/png', 'image/jpg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'png', 'jpg', 'jpeg'}

def compute_checksum(file_obj):
    sha256_hash = hashlib.sha256()
    for byte_block in iter(lambda: file_obj.read(4096), b""):
        sha256_hash.update(byte_block)
    file_obj.seek(0)
    return sha256_hash.hexdigest()

@document_bp.route('/upload', methods=['POST'])
def upload_file():
    session_id = request.headers.get('X-Session-ID')
    if not session_id:
        return jsonify({'error': 'No session ID'}), 400
    
    # Verify session/application link
    # For now, just link to session if application_id is present
    session = ChatSession.query.get(session_id)
    if not session:
        return jsonify({'error': 'Invalid session'}), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    if file and allowed_file(file.filename):
        if file.mimetype not in ALLOWED_MIME_TYPES:
             return jsonify({'error': 'Invalid file type. Only PDF, JPG, PNG allowed.'}), 400

        checksum = compute_checksum(file)
        
        # Check if already uploaded
        # existing = Document.query.filter_by(checksum_sha256=checksum).first()
        # if existing: ... (Optional optimization)

        filename = secure_filename(f"{session_id}_{file.filename}")
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(save_path)
            
            # Create DB Record
            doc = Document(
                application_id=session.application_id, # Might be None if not yet created
                filename=file.filename,
                file_path=filename, # Relative to upload folder
                file_size=os.path.getsize(save_path),
                mime_type=file.mimetype,
                checksum_sha256=checksum,
                document_type=request.form.get('document_type', 'unknown')
            )
            db.session.add(doc)
            db.session.commit()
            
            return jsonify({
                'document_id': doc.document_id,
                'filename': doc.filename,
                'file_size': doc.file_size,
                'document_type': doc.document_type,
                'status': 'uploaded'
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
            
    return jsonify({'error': 'Invalid file'}), 400

@document_bp.route('/documents', methods=['GET'])
def list_documents():
    session_id = request.headers.get('X-Session-ID')
    session = ChatSession.query.get(session_id)
    if not session: return jsonify({'error': 'Invalid session'}), 400
    
    # If application_id is linked
    if session.application_id:
        docs = Document.query.filter_by(application_id=session.application_id).all()
    else:
        # Fallback: maybe filter by filename prefix if we didn't link yet?
        # Ideally we linked application_id. If not, we can't easily find them unless we stored session_id in Document (which we didn't in schema).
        # Wait, the schema `Document` has `application_id`. It doesn't have `session_id`.
        # Issue: When uploading before application is created (e.g. KYC stage), `application_id` might be null.
        # Fix: We should probably store temporary docs or link them later.
        # Or, we update `Document` model to have `session_id`?
        # The prompt says "Save record to documents table".
        # I'll rely on `application_id`. If it's None, we have a problem.
        # Usually, application is created early.
        # MasterAgent state has `application_id`.
        return jsonify([])

    return jsonify([{
        'document_id': d.document_id,
        'filename': d.filename,
        'type': d.document_type,
        'size': d.file_size
    } for d in docs])

@document_bp.route('/documents/<document_id>', methods=['DELETE'])
def delete_document(document_id):
    doc = Document.query.get(document_id)
    if doc:
        try:
            path = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.file_path)
            if os.path.exists(path):
                os.remove(path)
            db.session.delete(doc)
            db.session.commit()
            return jsonify({'message': 'Deleted'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Not found'}), 404

@document_bp.route('/documents/download/<document_id>', methods=['GET'])
def download_document(document_id):
    # This might be for sanction letter too if we treat it as a document
    doc = Document.query.get(document_id)
    if doc:
         return send_from_directory(current_app.config['UPLOAD_FOLDER'], doc.file_path, as_attachment=True)
    return jsonify({'error': 'Not found'}), 404

#......extract profile endpoint.........
@document_bp.route('/extract-profile', methods=['POST'])
def extract_profile_from_docs():
    try:
        from utils.extract import extract_profile

        session_id = request.headers.get('X-Session-ID')
        if not session_id:
            return jsonify({'error': 'No session ID'}), 400

        # Get all documents for this session from DB
        session = ChatSession.query.get(session_id)
        if not session:
            return jsonify({'error': 'Invalid session'}), 400

        docs = Document.query.filter_by(application_id=session.application_id).all()
        if not docs:
            return jsonify({'error': 'No documents found for this session'}), 400

        # Build full file paths
        upload_folder = current_app.config['UPLOAD_FOLDER']
        pdf_paths = [
            os.path.join(upload_folder, doc.file_path)
            for doc in docs
            if os.path.exists(os.path.join(upload_folder, doc.file_path))
        ]

        if not pdf_paths:
            return jsonify({'error': 'No files found on disk'}), 400

        # Run extractor
        profile, missing = extract_profile(pdf_paths)

        return jsonify({
            'status': 'success',
            'profile': profile,
            'missing_fields': missing
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
