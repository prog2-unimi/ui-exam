bind = '0.0.0.0:8000'
workers = 1  # in-process @cache: a second worker would not share it
preload_app = True  # warm up in create_app() before the port is bound
accesslog = '-'
errorlog = '-'
loglevel = 'info'
