from peewee import (
    SqliteDatabase, Model, FloatField, IntegerField,
    CharField, DateTimeField
)
from datetime import datetime

db = SqliteDatabase("weather.db")


class Weather(Model):
    temp = FloatField()
    humidity = IntegerField(null=True)
    description = CharField(max_length=50)
    pressure = IntegerField(null=True)
    icon = CharField(max_length=20)
    city = CharField(max_length=100)
    date = DateTimeField(default=datetime.now)

    class Meta:
        database = db
        table_name = "weather"


db.connect(reuse_if_open=True)
db.create_tables([Weather])
