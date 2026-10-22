"""Password hashing and verification."""

import secrets
import string
from typing import Any

from passlib.context import CryptContext

from auth.errors import PasswordTooWeakError


class PasswordHasher:
    """Secure password hashing using bcrypt.
    
    This class provides methods for hashing and verifying passwords
    using the bcrypt algorithm, which is currently the most secure option.
    """
    
    def __init__(self, schemes: list[str] | None = None):
        """Initialize the password hasher.
        
        Args:
            schemes: List of hashing schemes to support. Defaults to bcrypt.
        """
        self.context = CryptContext(schemes=schemes or ["bcrypt"], deprecated=["auto"])
    
    def hash(self, password: str) -> str:
        """Hash a password.
        
        Args:
            password: The password to hash
            
        Returns:
            The hashed password
        """
        return self.context.hash(password)
    
    def verify(self, password: str, hash: str) -> bool:
        """Verify a password against a hash.
        
        Args:
            password: The password to verify
            hash: The stored hash to verify against
            
        Returns:
            True if the password matches the hash, False otherwise
        """
        try:
            return self.context.verify(password, hash)
        except ValueError:
            # Hash is invalid or uses an unsupported scheme
            return False
    
    def needs_rehash(self, hash: str) -> bool:
        """Check if a hash needs to be rehashed.
        
        Args:
            hash: The stored hash to check
            
        Returns:
            True if the hash should be rehashed
        """
        return self.context.needs_update(hash)
    
    def identify(self, hash: str) -> str | None:
        """Identify the hashing scheme used for a hash.
        
        Args:
            hash: The hash to identify
            
        Returns:
            The scheme name or None if unknown
        """
        return self.context.identify(hash)


class PasswordValidator:
    """Password strength validation."""
    
    def __init__(
        self,
        min_length: int = 8,
        require_uppercase: bool = True,
        require_lowercase: bool = True,
        require_digit: bool = True,
        require_special: bool = True,
        max_length: int = 128,
    ):
        """Initialize the validator.
        
        Args:
            min_length: Minimum password length
            require_uppercase: Whether uppercase letters are required
            require_lowercase: Whether lowercase letters are required
            require_digit: Whether digits are required
            require_special: Whether special characters are required
            max_length: Maximum password length
        """
        self.min_length = min_length
        self.require_uppercase = require_uppercase
        self.require_lowercase = require_lowercase
        self.require_digit = require_digit
        self.require_special = require_special
        self.max_length = max_length
    
    def validate(self, password: str) -> tuple[bool, list[str]]:
        """Validate password strength.
        
        Args:
            password: The password to validate
            
        Returns:
            Tuple of (is_valid, list_of_error_reasons)
        """
        errors = []
        
        # Check length
        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters")
        if len(password) > self.max_length:
            errors.append(f"Password must be at most {self.max_length} characters")
        
        # Check character types
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in string.punctuation for c in password)
        
        if self.require_uppercase and not has_upper:
            errors.append("Password must contain at least one uppercase letter")
        if self.require_lowercase and not has_lower:
            errors.append("Password must contain at least one lowercase letter")
        if self.require_digit and not has_digit:
            errors.append("Password must contain at least one digit")
        if self.require_special and not has_special:
            errors.append("Password must contain at least one special character")
        
        # Check common patterns
        if self._is_common_password(password):
            errors.append("Password is too common")
        if self._is_sequential(password):
            errors.append("Password contains sequential characters")
        if self._is_repeated(password):
            errors.append("Password contains repeated characters")
        
        return len(errors) == 0, errors
    
    def validate_raise(self, password: str) -> None:
        """Validate password and raise error if invalid.
        
        Args:
            password: The password to validate
            
        Raises:
            PasswordTooWeakError: If password doesn't meet requirements
        """
        is_valid, errors = self.validate(password)
        if not is_valid:
            raise PasswordTooWeakError(errors)
    
    @staticmethod
    def _is_common_password(password: str) -> bool:
        """Check if password is in common passwords list."""
        # In production, this would use a more comprehensive list
        common = {
            "password", "123456", "12345678", "1234", "qwerty", "12345",
            "dragon", "baseball", "football", "letmein", "monkey",
            "abc123", "password1", "admin", "welcome", "login",
            "passw0rd", "master", "hello", "freedom", "whatever",
        }
        return password.lower() in common
    
    @staticmethod
    def _is_sequential(password: str) -> bool:
        """Check for sequential characters (123, abc, etc.)."""
        for i in range(len(password) - 2):
            # Check numeric sequences
            if (password[i].isdigit() and password[i+1].isdigit() and password[i+2].isdigit()):
                if (ord(password[i+1]) == ord(password[i]) + 1 and
                    ord(password[i+2]) == ord(password[i]) + 2):
                    return True
            # Check alphabetic sequences
            if (password[i].isalpha() and password[i+1].isalpha() and password[i+2].isalpha()):
                if (ord(password[i+1].lower()) == ord(password[i].lower()) + 1 and
                    ord(password[i+2].lower()) == ord(password[i].lower()) + 2):
                    return True
        return False
    
    @staticmethod
    def _is_repeated(password: str) -> bool:
        """Check for repeated character patterns."""
        # Check for same character repeated 3+ times
        for i in range(len(password) - 2):
            if password[i] == password[i+1] == password[i+2]:
                return True
        # Check for patterns like "ababab"
        for i in range(len(password) - 3):
            if password[i] == password[i+2]:
                # Check for repeating pattern of length 2
                if password[i:i+2] == password[i+2:i+4]:
                    return True
        return False


class PasswordGenerator:
    """Generate random secure passwords."""
    
    def __init__(
        self,
        min_length: int = 12,
        max_length: int = 16,
        include_uppercase: bool = True,
        include_lowercase: bool = True,
        include_digits: bool = True,
        include_special: bool = True,
    ):
        """Initialize the generator.
        
        Args:
            min_length: Minimum password length
            max_length: Maximum password length
            include_uppercase: Whether to include uppercase letters
            include_lowercase: Whether to include lowercase letters
            include_digits: Whether to include digits
            include_special: Whether to include special characters
        """
        self.min_length = min_length
        self.max_length = max_length
        self.include_uppercase = include_uppercase
        self.include_lowercase = include_lowercase
        self.include_digits = include_digits
        self.include_special = include_special
        
        self._chars = ""
        if include_uppercase:
            self._chars += string.ascii_uppercase
        if include_lowercase:
            self._chars += string.ascii_lowercase
        if include_digits:
            self._chars += string.digits
        if include_special:
            self._chars += string.punctuation
    
    def generate(self) -> str:
        """Generate a random password.
        
        Returns:
            A randomly generated password
        """
        length = secrets.randbelow(self.max_length - self.min_length + 1) + self.min_length
        
        # Ensure at least one character from each required category
        password = []
        
        if self.include_uppercase:
            password.append(secrets.choice(string.ascii_uppercase))
        if self.include_lowercase:
            password.append(secrets.choice(string.ascii_lowercase))
        if self.include_digits:
            password.append(secrets.choice(string.digits))
        if self.include_special:
            password.append(secrets.choice(string.punctuation))
        
        # Fill the rest with random characters
        while len(password) < length:
            password.append(secrets.choice(self._chars))
        
        # Shuffle to avoid predictable patterns
        secrets.SystemRandom().shuffle(password)
        
        return "".join(password)
    
    def generate_multiple(self, count: int = 5) -> list[str]:
        """Generate multiple random passwords.
        
        Args:
            count: Number of passwords to generate
            
        Returns:
            List of generated passwords
        """
        return [self.generate() for _ in range(count)]


# =============================================================================
# MODULE-LEVEL INSTANCES
# =============================================================================

# Default password hasher instance
default_hasher = PasswordHasher()

# Default password validator instance
default_validator = PasswordValidator()

# Default password generator instance
default_generator = PasswordGenerator()
