from marshmallow import Schema, fields, validate, ValidationError
from flask import abort

class KYCSchema(Schema):
    pan_no = fields.Str(required=True, validate=validate.Regexp(r'^[A-Z]{5}[0-9]{4}[A-Z]$'))
    aadhaar_no = fields.Str(required=True, validate=validate.Regexp(r'^[0-9]{12}$'))

    @classmethod
    def validate_and_raise(cls, data):
        schema = cls()
        try:
            return schema.load(data)
        except ValidationError as err:
            abort(400, description=err.messages)

class LoanApplicationSchema(Schema):
    loan_amount = fields.Float(required=True, validate=validate.Range(min=10000, max=10000000))
    tenure_months = fields.Int(required=True, validate=validate.Range(min=3, max=360))
    credit_score = fields.Int(validate=validate.Range(min=300, max=900))
    monthly_income = fields.Float(required=True, validate=validate.Range(min=0))
    email = fields.Email()
    phone = fields.Str(required=True, validate=validate.Regexp(r'^[6-9][0-9]{9}$'))

    @classmethod
    def validate_and_raise(cls, data):
        schema = cls()
        try:
            return schema.load(data)
        except ValidationError as err:
            abort(400, description=err.messages)

class LoginSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=3))
    password = fields.Str(required=True, validate=validate.Length(min=6))

    @classmethod
    def validate_and_raise(cls, data):
        schema = cls()
        try:
            # marshmallow doesn't have a 'strip' parameter in fields, we'll do it manually if needed or in auth.py
            return schema.load(data)
        except ValidationError as err:
            abort(400, description=err.messages)
