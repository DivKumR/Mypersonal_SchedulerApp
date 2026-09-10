#  Ensures the agent returns a validated object instead of an untrusted dictionary.

from datetime import date, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentAction(str, Enum):
	CREATE_EVENT = "create_event"
	GET_EVENTS = "get_events"
	UNKNOWN = "unknown"


class EventDetails(BaseModel):
	model_config = ConfigDict(extra="forbid")

	event_id: Optional[str] = None
	date: Optional[date] = None
	name: Optional[str] = None
	activity: Optional[str] = None
	start_time: Optional[time] = None
	end_time: Optional[time] = None


class AgentResponse(BaseModel):
	model_config = ConfigDict(extra="forbid")

	action: AgentAction
	message: str
	event: Optional[EventDetails] = None
	requires_confirmation: bool = False
	missing_fields: list[str] = Field(default_factory=list)

	@model_validator(mode="after")
	def validate_create_event(self):
		if self.action == AgentAction.CREATE_EVENT:
			if self.event is None:
				raise ValueError("event is required for create_event")

			required = {
				"date": self.event.date,
				"name": self.event.name,
				"activity": self.event.activity,
				"start_time": self.event.start_time,
				"end_time": self.event.end_time,
			}

			missing = [key for key, value in required.items() if value is None]

			if missing:
				self.missing_fields = sorted(
					set(self.missing_fields + missing)
				)
				self.requires_confirmation = False

		return self