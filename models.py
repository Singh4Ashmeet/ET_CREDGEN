from database import db
from datetime import datetime, timedelta
import uuid
import json
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET

class Customer(db.Model):
    __tablename__ = 'customers'
    customer_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    age = db.Column(db.SmallInteger)
    gender = db.Column(db.String(20))
    marital_status = db.Column(db.String(20))
    dependents = db.Column(db.SmallInteger, default=0)
    education_level = db.Column(db.String(50))
    phone = db.Column(db.String(15), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    applications = db.relationship('LoanApplication', back_populates='customer')
    kyc_records = db.relationship('KYCRecord', back_populates='customer')
    loan_history = db.relationship('LoanHistory', back_populates='customer')

class LoanApplication(db.Model):
    __tablename__ = 'loan_applications'
    application_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.customer_id'))
    loan_type = db.Column(db.String(50))
    loan_amount = db.Column(db.Numeric(15, 2), nullable=False)
    tenure_months = db.Column(db.SmallInteger)
    interest_rate_requested = db.Column(db.Numeric(5, 2))
    purpose = db.Column(db.String(255))
    application_date = db.Column(db.Date, default=datetime.utcnow().date)
    address = db.Column(db.Text)
    pincode = db.Column(db.String(10))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    employment_type = db.Column(db.String(50))
    employer_name = db.Column(db.String(255))
    monthly_income = db.Column(db.Numeric(15, 2))
    other_income = db.Column(db.Numeric(15, 2), default=0)
    monthly_obligations = db.Column(db.Numeric(15, 2), default=0)
    credit_score = db.Column(db.SmallInteger)
    credit_score_agency = db.Column(db.String(30), default='CIBIL')
    num_active_loans = db.Column(db.SmallInteger, default=0)
    num_closed_loans = db.Column(db.SmallInteger, default=0)
    num_enquiries_6m = db.Column(db.SmallInteger, default=0)
    status = db.Column(db.String(30), default='initiated')
    rejection_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = db.relationship('Customer', back_populates='applications')
    kyc_record = db.relationship('KYCRecord', back_populates='application', uselist=False)
    fraud_check = db.relationship('FraudCheck', back_populates='application', uselist=False)
    underwriting_result = db.relationship('UnderwritingResult', back_populates='application', uselist=False)
    offers = db.relationship('LoanOffer', back_populates='application')
    documents = db.relationship('Document', back_populates='application')
    sanction_letter = db.relationship('SanctionLetter', back_populates='application', uselist=False)
    chat_sessions = db.relationship('ChatSession', back_populates='application')

class KYCRecord(db.Model):
    __tablename__ = 'kyc_records'
    kyc_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_applications.application_id'), unique=True)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.customer_id'))
    pan_no = db.Column(db.String(10), nullable=False)
    aadhaar_no = db.Column(db.String(12), nullable=False)
    dob_from_aadhaar = db.Column(db.Date)
    name_on_pan = db.Column(db.String(255))
    name_on_aadhaar = db.Column(db.String(255))
    address_on_aadhaar = db.Column(db.Text)
    pincode_on_aadhaar = db.Column(db.String(10))
    pan_verified = db.Column(db.Boolean, default=False)
    aadhaar_verified = db.Column(db.Boolean, default=False)
    name_match_score = db.Column(db.Numeric(5, 4))
    address_match_score = db.Column(db.Numeric(5, 4))
    dob_age_match = db.Column(db.Boolean)
    pincode_match = db.Column(db.Boolean)
    verified_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    application = db.relationship('LoanApplication', back_populates='kyc_record')
    customer = db.relationship('Customer', back_populates='kyc_records')

class LoanHistory(db.Model):
    __tablename__ = 'loan_history'
    history_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.customer_id'))
    lender_name = db.Column(db.String(255))
    loan_type = db.Column(db.String(50))
    loan_amount = db.Column(db.Numeric(15, 2))
    disbursement_date = db.Column(db.Date)
    original_tenure = db.Column(db.SmallInteger)
    closure_date = db.Column(db.Date)
    status = db.Column(db.String(20))
    outstanding_amount = db.Column(db.Numeric(15, 2), default=0)
    emi_amount = db.Column(db.Numeric(15, 2))
    overdue_amount = db.Column(db.Numeric(15, 2), default=0)
    dpd_30 = db.Column(db.SmallInteger, default=0)
    dpd_60 = db.Column(db.SmallInteger, default=0)
    dpd_90 = db.Column(db.SmallInteger, default=0)
    settled = db.Column(db.Boolean, default=False)
    written_off = db.Column(db.Boolean, default=False)
    foreclosed = db.Column(db.Boolean, default=False)
    worst_dpd_ever = db.Column(db.SmallInteger)
    avg_dpd = db.Column(db.Numeric(5, 2))
    source = db.Column(db.String(30), default='bureau')
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    customer = db.relationship('Customer', back_populates='loan_history')

class DeviceMetadata(db.Model):
    __tablename__ = 'device_metadata'
    device_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    session_id = db.Column(db.String(64), nullable=False)
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_applications.application_id'))
    ip_address = db.Column(INET)
    user_agent = db.Column(db.Text)
    device_fingerprint = db.Column(db.String(128))
    browser = db.Column(db.String(50))
    os = db.Column(db.String(50))
    device_type = db.Column(db.String(20))
    geolocation_lat = db.Column(db.Numeric(9, 6))
    geolocation_lng = db.Column(db.Numeric(9, 6))
    geolocation_city = db.Column(db.String(100))
    timezone = db.Column(db.String(60))
    is_vpn = db.Column(db.Boolean, default=False)
    is_proxy = db.Column(db.Boolean, default=False)
    is_tor = db.Column(db.Boolean, default=False)
    is_emulator = db.Column(db.Boolean, default=False)
    ip_reputation_score = db.Column(db.Numeric(4, 3))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

class FraudCheck(db.Model):
    __tablename__ = 'fraud_checks'
    fraud_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_applications.application_id'), unique=True)
    fraud_score = db.Column(db.Numeric(5, 4), nullable=False)
    fraud_flag = db.Column(db.String(10))
    velocity_check = db.Column(db.Boolean)
    blacklist_check = db.Column(db.Boolean)
    id_mismatch_check = db.Column(db.Boolean)
    device_risk_check = db.Column(db.Boolean)
    anomaly_flags = db.Column(JSONB, default={})
    model_version = db.Column(db.String(30))
    checked_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    application = db.relationship('LoanApplication', back_populates='fraud_check')

class UnderwritingResult(db.Model):
    __tablename__ = 'underwriting_results'
    underwriting_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_applications.application_id'), unique=True)
    risk_score = db.Column(db.Numeric(5, 4), nullable=False)
    risk_band = db.Column(db.String(10))
    approval_status = db.Column(db.Boolean, nullable=False)
    interest_rate_offered = db.Column(db.Numeric(5, 2))
    max_eligible_amount = db.Column(db.Numeric(15, 2))
    approved_tenure_months = db.Column(db.SmallInteger)
    rejection_reason = db.Column(db.Text)
    model_version = db.Column(db.String(30))
    feature_importance = db.Column(JSONB, default={})
    underwritten_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    application = db.relationship('LoanApplication', back_populates='underwriting_result')

class LoanOffer(db.Model):
    __tablename__ = 'loan_offers'
    offer_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_applications.application_id'))
    loan_amount = db.Column(db.Numeric(15, 2), nullable=False)
    interest_rate = db.Column(db.Numeric(5, 2), nullable=False)
    tenure_months = db.Column(db.SmallInteger, nullable=False)
    monthly_emi = db.Column(db.Numeric(15, 2), nullable=False)
    processing_fee = db.Column(db.Numeric(15, 2), default=0)
    total_payable = db.Column(db.Numeric(15, 2))
    offer_type = db.Column(db.String(20), default='standard')
    offer_version = db.Column(db.SmallInteger, default=1)
    accepted = db.Column(db.Boolean, default=False)
    accepted_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    application = db.relationship('LoanApplication', back_populates='offers')
    sanction_letters = db.relationship('SanctionLetter', back_populates='offer')

class Document(db.Model):
    __tablename__ = 'documents'
    document_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_applications.application_id'))
    document_type = db.Column(db.String(50))
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.BigInteger)
    mime_type = db.Column(db.String(100))
    checksum_sha256 = db.Column(db.String(64))
    is_verified = db.Column(db.Boolean, default=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    application = db.relationship('LoanApplication', back_populates='documents')

class SanctionLetter(db.Model):
    __tablename__ = 'sanction_letters'
    letter_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_applications.application_id'), unique=True)
    offer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_offers.offer_id'))
    sanction_number = db.Column(db.String(30), unique=True, nullable=False)
    pdf_path = db.Column(db.String(512))
    generated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    valid_until = db.Column(db.Date)
    signed_by_customer = db.Column(db.Boolean, default=False)
    signed_at = db.Column(db.DateTime(timezone=True))
    disbursed = db.Column(db.Boolean, default=False)
    disbursed_amount = db.Column(db.Numeric(15, 2))
    disbursed_at = db.Column(db.DateTime(timezone=True))
    disbursal_ref = db.Column(db.String(100))

    application = db.relationship('LoanApplication', back_populates='sanction_letter')
    offer = db.relationship('LoanOffer', back_populates='sanction_letters')

class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    session_id = db.Column(db.String(64), PRIMARY KEY=True)
    application_id = db.Column(UUID(as_uuid=True), db.ForeignKey('loan_applications.application_id'))
    state = db.Column(JSONB, nullable=False, default={})
    stage = db.Column(db.String(50))
    interaction_count = db.Column(db.Integer, default=0)
    workflow_history = db.Column(JSONB, default=[])
    last_activity = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.utcnow() + timedelta(minutes=30))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    application = db.relationship('LoanApplication', back_populates='chat_sessions')
    logs = db.relationship('ChatLog', back_populates='session')

    def get_state(self):
        return self.state

    def set_state(self, state_dict):
        self.state = state_dict

    def touch(self):
        self.last_activity = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(minutes=30)

    def is_expired(self):
        return self.expires_at < datetime.utcnow()

class ChatLog(db.Model):
    __tablename__ = 'chat_logs'
    log_id = db.Column(db.BigInteger, PRIMARY KEY=True, autoincrement=True)
    session_id = db.Column(db.String(64), db.ForeignKey('chat_sessions.session_id'))
    event_type = db.Column(db.String(50))
    message_role = db.Column(db.String(20))
    message_text = db.Column(db.Text)
    status = db.Column(db.String(30))
    details = db.Column(JSONB, default={})
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    session = db.relationship('ChatSession', back_populates='logs')

class AdminUser(db.Model):
    __tablename__ = 'admin_users'
    user_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), default='viewer')
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime(timezone=True))
    failed_logins = db.Column(db.SmallInteger, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    tuning_contents = db.relationship('TuningContent', back_populates='admin')

    def set_password(self, plain_text):
        self.password_hash = generate_password_hash(plain_text, method='pbkdf2:sha256:600000')

    def check_password(self, plain_text):
        return check_password_hash(self.password_hash, plain_text)

    def is_locked(self):
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

    def record_failed_login(self):
        self.failed_logins += 1
        if self.failed_logins >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)
            self.failed_logins = 0

    def record_successful_login(self):
        self.failed_logins = 0
        self.locked_until = None
        self.last_login = datetime.utcnow()

class RevokedToken(db.Model):
    __tablename__ = 'revoked_tokens'
    id = db.Column(db.Integer, PRIMARY KEY=True, autoincrement=True)
    jti = db.Column(db.String(120), unique=True, nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    @classmethod
    def is_revoked(cls, jti):
        return cls.query.filter_by(jti=jti).first() is not None

class TuningContent(db.Model):
    __tablename__ = 'tuning_content'
    content_id = db.Column(UUID(as_uuid=True), PRIMARY KEY=True, default=uuid.uuid4)
    admin_id = db.Column(UUID(as_uuid=True), db.ForeignKey('admin_users.user_id'))
    type = db.Column(db.String(50))
    content = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    admin = db.relationship('AdminUser', back_populates='tuning_contents')
