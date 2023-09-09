import requests
from datetime import datetime
from urllib.parse import urlencode
import time

# replace with your user info bellow
# and in command line, run `python dps_check_availability.py`
email = 'xxxx@gmail.com'
first_name = 'John'
last_name = 'Doe'
date_of_birth = 'MM/DD/YYYY'
last4ssn = '0000'
zipcode = '78750'
cell_phone = '0000000000'

type_id = 71 # service type id, 71 for new driver's license, 81 for renew license, 21 for road test.
distance = 10 # How far from the zipcode. unit in miles

check_interval = 60 # in seconds, check every 60 seconds.

data = {'TypeId': type_id, 'ZipCode': zipcode, 'CityName': '', 'PreferredDay': '0'}
credential = {'FirstName': first_name, 'LastName': last_name, 'DateOfBirth': date_of_birth, 'Last4Ssn': last4ssn}
headers = {
  "Host": "publicapi.txdpsscheduler.com",
  "Connection": "keep-alive",
  "Content-Length": "62",
  "sec-ch-ua": "' Not A;Brand';v='99', 'Chromium';v='99', 'Google Chrome';v='99'",
  "Accept": "application/json, text/plain, */*",
  "Content-Type": "application/json;charset=UTF-8",
  "sec-ch-ua-mobile": "?0",
  "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36",
  "sec-ch-ua-platform": "macOS",
  "Origin": "https://public.txdpsscheduler.com",
  "Sec-Fetch-Site": "same-site",
  "Sec-Fetch-Mode": "cors",
  "Sec-Fetch-Dest": "empty",
  "Referer": "https://public.txdpsscheduler.com/",
  "Accept-Encoding": "gzip, deflate, br",
  "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"
}

# default cur appointment date
cur_date = datetime.now()
cur_appointment_date = datetime(cur_date.year + 1, cur_date.month, cur_date.day)

def send_request(url, payload):
  response = requests.post(url, data=str(payload), headers=headers)
  try:
    response.raise_for_status()
  except requests.exceptions.HTTPError as e:
    print("[Error] " + str(e))
    return None
  return response.json()

# login
print("loging in....")
try:
  payload = {
    'DateOfBirth': date_of_birth,
    'FirstName': first_name,
    'LastName': last_name,
    'LastFourDigitsSsn': last4ssn,
  }
  eligibility = send_request(url='https://publicapi.txdpsscheduler.com/api/Eligibility', payload=payload)
  if not eligibility:
    print("[Error] Login failed.")
    exit()
  responseId = eligibility[0]['ResponseId']
  print("Login succeed (%s)..." % responseId)
  appointments = send_request(url='https://publicapi.txdpsscheduler.com/api/Booking', payload=payload)
  if not appointments:
    print("No existing appointment found.")
  else:
    print("Existing appointment dates: %s" % appointments[0]['BookingDateTime'])
    cur_appointment_date = datetime.strptime(appointments[0]['BookingDateTime'][:10], "%Y-%m-%d")
except requests.exceptions.HTTPError as e:
  print('login failed.', e.response.text)

rescheduled = False

def checkAvailability():
  global rescheduled
  global cur_appointment_date
  global distance
  # get available locations
  print("Fetching available locations...")
  locations = send_request('https://publicapi.txdpsscheduler.com/api/AvailableLocation', payload=data)
  if not type(locations)==list:
    print("[Error] failed to request available locations.")
    return
  locations.sort(key=lambda l:datetime.strptime(l['NextAvailableDate'], '%m/%d/%Y'))
  # filter out locations that are too distant.
  locations = [location for location in locations if location['Distance'] < distance]

  # refresh current appointment
  if rescheduled:
    print("Fetching current appointment...")
    payload = {
      'DateOfBirth': date_of_birth,
      'FirstName': first_name,
      'LastName': last_name,
      'LastFourDigitsSsn': last4ssn,
    }
    appointments = send_request(url='https://publicapi.txdpsscheduler.com/api/Booking', payload=payload)
    if not appointments:
      print("No existing appointment found.")
    else:
      print("Existing appointment dates: %s" % appointments[0]['BookingDateTime'])
      cur_appointment_date = datetime.strptime(appointments[0]['BookingDateTime'][:10], "%Y-%m-%d")

  # check for available dates
  for location in locations:
    next_available_date = datetime.strptime(location['NextAvailableDate'], '%m/%d/%Y')
    if next_available_date < cur_appointment_date:
      print("Ealier available date found in %s (%s miles) at %s" % (location['Name'], location['Distance'], location['NextAvailableDate']))
      availability = location['Availability']
      if not availability:
        print("Fetching availability...")
        payload = {'TypeId': type_id, 'LocationId': location['Id']}
        availability = send_request(url='https://publicapi.txdpsscheduler.com/api/AvailableLocationDates', payload=payload)
      if not availability:
        print("[Error] failed to request availability.")
        continue
      if availability['LocationAvailabilityDates']:
        time_slots = availability['LocationAvailabilityDates'][0]['AvailableTimeSlots']
        if len(time_slots) > 0:
          selected_slot_id = time_slots[-1]['SlotId'] # choose the last time slot
          scheduled_time = time_slots[-1]['StartDateTime']
          # hold slot
          print("Holding your slots(%s) at %s." % (selected_slot_id, scheduled_time))
          payload = {**credential, "SlotId": selected_slot_id}
          hold_status = send_request(url='https://publicapi.txdpsscheduler.com/api/HoldSlot', payload=payload)
          if not hold_status:
            print("[Error] Hold slots failed.")
            continue
          print('Hold status:', hold_status['SlotHeldSuccessfully'])
          if hold_status['SlotHeldSuccessfully']:
            print("Rescheduling...")
            payload = {
              **credential,
              'Email': email,
              'ServiceTypeId': type_id,
              'BookingDateTime': scheduled_time,
              'BookingDuration': time_slots[-1]['Duration'],
              'SpanishLanguage': 'N',
              'SiteId': location['Id'],
              'ResponseId': responseId,
              'CardNumber': '',
              'CellPhone': cell_phone,
              'HomePhone': '',
              'SendSms': True,
            }
            try:
              reschedule_status = send_request(url='https://publicapi.txdpsscheduler.com/api/RescheduleBooking', payload=payload)
              rescheduled = True
              print("Reschedule succeed, check your email for appointment details.")
              break
            except requests.exceptions.HTTPError as e:
              print('Reschedule failed.', e.response.text)
          else:
            print("Hold slots failed.")

  if not rescheduled:
    print("No ealier date found.")


def startChecking():
  lookup_cnt = 0
  while True:
    print("Start checking:", lookup_cnt)
    checkAvailability()
    lookup_cnt += 1
    time.sleep(check_interval)

startChecking()

