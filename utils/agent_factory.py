from agents.master_agent import MasterAgent
from agents.underwriting_agent import UnderwritingAgent
from agents.fraud_agent import FraudAgent
from agents.sales_agent import SalesAgent
import logging

logger = logging.getLogger(__name__)

class AgentManager:
    _master_agent = None
    _underwriting_agent = None
    _fraud_agent = None
    _sales_agent = None

    @classmethod
    def get_master_agent(cls):
        return MasterAgent()

    @classmethod
    def get_underwriting_agent(cls):
        if cls._underwriting_agent is None:
            logger.info("Initializing UnderwritingAgent singleton...")
            cls._underwriting_agent = UnderwritingAgent()
        return cls._underwriting_agent

    @classmethod
    def get_fraud_agent(cls):
        if cls._fraud_agent is None:
            logger.info("Initializing FraudAgent singleton...")
            cls._fraud_agent = FraudAgent()
        return cls._fraud_agent

    @classmethod
    def get_sales_agent(cls):
        if cls._sales_agent is None:
            logger.info("Initializing SalesAgent singleton...")
            cls._sales_agent = SalesAgent()
        return cls._sales_agent

def get_master_agent():
    return AgentManager.get_master_agent()

def get_underwriting_agent():
    return AgentManager.get_underwriting_agent()

def get_fraud_agent():
    return AgentManager.get_fraud_agent()

def get_sales_agent():
    return AgentManager.get_sales_agent()
