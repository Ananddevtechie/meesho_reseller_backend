import json

import httpx

from app.config import settings
from app.schemas import ExtractedAddress


class GeminiExtractionError(RuntimeError):
	"""Raised when Gemini cannot provide an address extraction."""


async def extract_address(text: str) -> ExtractedAddress:
	if not settings.gemini_api_key:
		raise GeminiExtractionError('GEMINI_API_KEY is not configured.')

	prompt = '''Extract the shipping address from the note below. Return only valid JSON with exactly these string keys:
name, address, district, pin, mobile.
The address may contain multiple lines; preserve them as a single string separated by newline characters.
Do not invent missing values. Remove labels such as "Pin", "No", and punctuation around values.

Note:
''' + text
	url = (
		'https://generativelanguage.googleapis.com/v1beta/models/'
		f'{settings.gemini_model}:generateContent'
	)
	payload = {
		'contents': [{'parts': [{'text': prompt}]}],
		'generationConfig': {
			'temperature': 0,
			'responseMimeType': 'application/json',
		},
	}

	try:
		async with httpx.AsyncClient(timeout=20) as client:
			response = await client.post(
				url,
				params={'key': settings.gemini_api_key},
				json=payload,
			)
			response.raise_for_status()
			body = response.json()
			generated = body['candidates'][0]['content']['parts'][0]['text']
			print('Address extraction: generated from Gemini.')
			return ExtractedAddress.model_validate(json.loads(generated))
	except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
		print(f'Address extraction: Gemini failed ({type(error).__name__}).')
		raise GeminiExtractionError('Gemini could not extract this address.') from error
