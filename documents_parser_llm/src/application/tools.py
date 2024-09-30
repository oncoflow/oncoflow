import time
from functools import wraps

def timed(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        start = time.time()
        result = func(self, *args, **kwargs)
        end = time.time()

        seconds = round(end - start, 2)
        minutes = int((seconds % 3600) // 60)
        hours = int(seconds // 3600)
        remaining_seconds = round(seconds % 60)

        # Build the formatted time string
        formatted_time = ""
        if hours > 0:
            formatted_time += f"{hours}h"
        if minutes > 0:
            formatted_time += f"{minutes}min"
        if remaining_seconds > 0:
            formatted_time += f"{remaining_seconds}sec"
        if formatted_time == "":
            formatted_time = "0"
            
        logger_extra = self.logger_default_extra if hasattr(self, "logger_default_extra") else None

        self.logger.info(
            f"{func.__name__} ran in {formatted_time}", extra=logger_extra
        )
        
        if hasattr(self, "metadata"):
            if isinstance(self.metadata, dict):
                self.metadata[func.__name__] = {
                    "time": seconds,
                    "model": self.current_model if hasattr(self, "current_model") else "Not set",
                    "ressources": self.additional_pdf if hasattr(self, "additional_pdf") else "Not set"
                }
        
        return result

    return wrapper

