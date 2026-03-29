from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required, 
    get_jwt_identity, get_jwt, get_current_user
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from utils.database import db
from models.db_models import AdminUser, RevokedToken
from datetime import datetime
import os

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
limiter = Limiter(key_func=get_remote_address)

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"message": "Invalid credentials or account locked"}), 401

    username = data.get('username').strip()
    password = data.get('password')

    user = AdminUser.query.filter_by(username=username).first()

    # Generic error message to prevent user enumeration
    generic_error = {"message": "Invalid credentials or account locked"}

    if not user or not user.is_active:
        return jsonify(generic_error), 401

    if user.is_locked():
        return jsonify(generic_error), 401

    if not user.check_password(password):
        user.record_failed_login()
        db.session.commit()
        return jsonify(generic_error), 401

    # Success
    user.record_successful_login()
    db.session.commit()

    access_token = create_access_token(
        identity=str(user.user_id), 
        additional_claims={"role": user.role, "username": user.username}
    )
    refresh_token = create_refresh_token(identity=str(user.user_id))

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "role": user.role,
        "username": user.username
    }), 200

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    user = AdminUser.query.get(identity)
    if not user or not user.is_active:
         return jsonify({"message": "User not found or inactive"}), 401
         
    new_access_token = create_access_token(
        identity=identity,
        additional_claims={"role": user.role, "username": user.username}
    )
    return jsonify({"access_token": new_access_token}), 200

@auth_bp.route('/logout', methods=['DELETE'])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    revoked_token = RevokedToken(jti=jti)
    try:
        db.session.add(revoked_token)
        db.session.commit()
        return jsonify({"message": "Logged out"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "server_error", "message": "Logout failed"}), 500

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = AdminUser.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404
        
    return jsonify({
        "user_id": str(user.user_id),
        "username": user.username,
        "email": user.email,
        "role": user.role
    }), 200

@auth_bp.route('/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    user = AdminUser.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json()
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({"message": "Both old and new passwords are required"}), 400

    if len(new_password) < 8:
        return jsonify({"message": "New password must be at least 8 characters"}), 400

    if not user.check_password(old_password):
        return jsonify({"message": "Current password is incorrect"}), 401

    try:
        user.set_password(new_password)
        db.session.commit()
        return jsonify({"message": "Password changed successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "Failed to change password"}), 500
