# Copyright (C) 2025, Mebin J Thattil <mail@mebin.in>
# This file is part of Speak.activity
#
#     Speak.activity is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     Speak.activity is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with Speak.activity.  If not, see <http://www.gnu.org/licenses/>.

import base64
import os

def encode(string):
    return base64.b64encode(string.encode('utf-8'))
    
def decode(string):
    return base64.b64decode(string.encode('utf-8'))

def bad_word_list() -> list:
    with open(os.path.join(os.path.dirname(__file__), "profainity_blacklist.txt"), "r") as f: #the main reason why we have it encoded in b64 is so that even if a kid stumbles across this txt file by mistake they wont be able to understand anything
        a = f.readlines()
    decoded_list = [base64.b64decode(line.strip()).decode('utf-8') for line in a]

    return decoded_list

def is_profane(text: str) -> bool:
        """
        Check if the given string contains any profanity from the blacklist (whole word match only).
        """
        words = [w.strip(".,!?;:()[]{}\"'").lower() for w in text.split()]
        blacklist = set(word.lower() for word in bad_word_list())
        for w in words:
            if w in blacklist:
                return False
        return True
