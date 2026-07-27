import logging
from typing import Optional
from database.database import Database
from database.models import Payment, User

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.db = Database
    
    async def process_payment(self, user_id: int, amount: int, screenshot_file_id: str) -> int:
        """Process new payment request"""
        try:
            payment_id = await self.db.create_payment(user_id, amount, screenshot_file_id)
            logger.info(f"Payment created: {payment_id} for user {user_id}, amount {amount}")
            return payment_id
        except Exception as e:
            logger.error(f"Error processing payment: {e}")
            raise
    
    async def approve_payment(self, payment_id: int) -> bool:
        """Approve payment and add balance to user"""
        try:
            # Get payment details
            payment = await self.db.get_payment_by_id(payment_id)
            if not payment:
                logger.error(f"Payment {payment_id} not found")
                return False
            
            if payment.status != 'pending':
                logger.error(f"Payment {payment_id} is not pending")
                return False
            
            # Update payment status
            await self.db.update_payment_status(payment_id, 'approved')
            
            # Add balance to user
            user = await self.db.get_user_by_id(payment.user_id)
            if user:
                await self.db.update_user_balance(user.telegram_id, payment.amount)
                logger.info(f"Payment {payment_id} approved, {payment.amount} added to user {user.telegram_id}")
                return True
            else:
                logger.error(f"User {payment.user_id} not found for payment {payment_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error approving payment {payment_id}: {e}")
            return False
    
    async def reject_payment(self, payment_id: int) -> bool:
        """Reject payment"""
        try:
            # Update payment status
            await self.db.update_payment_status(payment_id, 'rejected')
            logger.info(f"Payment {payment_id} rejected")
            return True
            
        except Exception as e:
            logger.error(f"Error rejecting payment {payment_id}: {e}")
            return False
    
    async def get_pending_payments(self):
        """Get all pending payments"""
        try:
            return await self.db.get_pending_payments()
        except Exception as e:
            logger.error(f"Error getting pending payments: {e}")
            return []
    
    async def check_user_balance(self, user_id: int, required_amount: int) -> bool:
        """Check if user has sufficient balance"""
        try:
            user = await self.db.get_user(user_id)
            if not user:
                return False
            
            return user.balance >= required_amount
            
        except Exception as e:
            logger.error(f"Error checking user balance: {e}")
            return False
    
    async def deduct_balance(self, user_id: int, amount: int) -> bool:
        """Deduct amount from user balance"""
        try:
            await self.db.update_user_balance(user_id, -amount)
            logger.info(f"Deducted {amount} from user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deducting balance: {e}")
            return False
