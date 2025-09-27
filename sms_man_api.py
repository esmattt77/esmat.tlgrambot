# sms_man_api.py
import requests
import json
import logging

# تهيئة نظام التسجيل
logger = logging.getLogger(__name__)

class SMSManAPI:
    """
    كلاس للتعامل مع واجهة برمجة التطبيقات (API) لخدمة SMS Man (مثل class.php).
    """
    
    _BASE_URL = "https://api.sms-man.com/stubs/handler_api.php"
    
    _ERROR_LIST = [
        "BAD_KEY", "BAD_ACTION", "NO_ACTIVATION", "NO_NUMBERS",
        "STATUS_WAIT_CODE", "STATUS_CANCEL", "NO_BALANCE", "BAD_STATUS",
        "STATUS_WAIT_RESEND", "STATUS_WAIT_RETRY", "ERROR_SQL",
    ]

    def __init__(self, api_key: str):
        self.link = f"{self._BASE_URL}?api_key={api_key}"

    def _is_error(self, data: str) -> bool:
        """التحقق مما إذا كانت الاستجابة تحتوي على كلمة خطأ."""
        data_upper = data.upper()
        # نستخدم any للتحقق من وجود أي خطأ في النص
        return not any(error in data_upper for error in self._ERROR_LIST)

    def _make_request(self, action: str, params: dict = None) -> str:
        """دالة مساعدة لإجراء طلب GET."""
        url = f"{self.link}&action={action}"
        if params:
            # إضافة المعاملات (parameters) للرابط
            for key, value in params.items():
                url += f"&{key}={value}"
        
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            return response.text.strip()
        except requests.exceptions.RequestException as e:
            logger.error(f"API Request Error: {e} on {action}")
            return f"REQUEST_ERROR:{e}"


    def get_number(self, country_code: str, service_code: str) -> dict:
        """شراء رقم لخدمة ودولة محددة (مثل getNumber في PHP)."""
        params = {"service": service_code, "country": country_code}
        get_data = self._make_request("getNumber", params=params)
        
        if self._is_error(get_data):
            # الاستجابة الناجحة: ACCESS_NUMBER:ID:NUMBER
            try:
                parts = get_data.split(":")
                id_op = parts[1]
                number = parts[2]
                return {"ok": True, "id": id_op, "number": number}
            except (IndexError, TypeError):
                return {"ok": False, "error": f"Failed to parse number data: {get_data}"}
        else:
            return {"ok": False, "error": get_data}

    def get_code(self, operation_id: int) -> dict:
        """الحصول على كود التفعيل (مثل getCode في PHP)."""
        params = {"id": operation_id}
        get_data = self._make_request("getStatus", params=params)
        
        if self._is_error(get_data):
            # الاستجابة الناجحة: STATUS_OK:code
            try:
                code = get_data.split(":")[-1]
                return {"ok": True, "code": code}
            except (IndexError, TypeError):
                return {"ok": False, "error": f"Failed to parse code: {get_data}"}
        else:
            return {"ok": False, "error": get_data}

    def cancel(self, operation_id: int) -> dict:
        """إلغاء العملية/حظر الرقم (مثل cencel في PHP)."""
        params = {"id": operation_id, "status": -1} 
        get_data = self._make_request("setStatus", params=params)
        
        if self._is_error(get_data):
            # الاستجابة الناجحة عادةً هي ACCESS_CANCEL
            return {"ok": True}
        else:
            return {"ok": False, "error": get_data}
