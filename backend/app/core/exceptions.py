class UserAlreadyExistsError(Exception):
    pass

class InvalidCredentialsError(Exception):
    pass

class InvalidAccessTokenError(Exception):
    pass

class IncidentNotFoundError(Exception):
    pass

class IncidentAssignmentError(Exception):
    pass

class UserNotFoundError(Exception):
    pass

class IncidentStatusUpdateError(Exception):
    pass

class CommentNotFoundError(Exception):
    pass

class CommentNotAllowedError(Exception):
    pass