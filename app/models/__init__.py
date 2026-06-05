from app.models.user import User
from app.models.portfolio import PortfolioState
from app.models.trade import Trade
from app.models.spending import SpendingRecord
from app.models.task import Task
from app.models.goal import Goal
from app.models.bill import Bill
from app.models.event_log import EventLog, ExecutionLog
from app.models.ticket import BotTicket
from app.models.memory import UserMemory

# Starfire One — new modules
from app.models.habit import Habit, HabitLog
from app.models.journal_entry import JournalEntry
from app.models.health_metric import HealthMetric
from app.models.business import Business, Customer, Project, Invoice
from app.models.knowledge_item import KnowledgeItem
from app.models.automation import Automation, AutomationRun
from app.models.audit_log import AuditLog
from app.models.net_worth_snapshot import NetWorthSnapshot
from app.models.agent_run import AgentRun
from app.models.email_watch import EmailWatch

__all__ = [
    "User", "PortfolioState", "Trade", "SpendingRecord", "Task", "Goal",
    "Bill", "EventLog", "ExecutionLog", "BotTicket", "UserMemory",
    # New
    "Habit", "HabitLog", "JournalEntry", "HealthMetric",
    "Business", "Customer", "Project", "Invoice",
    "KnowledgeItem", "Automation", "AutomationRun",
    "AuditLog", "NetWorthSnapshot", "AgentRun", "EmailWatch",
]
