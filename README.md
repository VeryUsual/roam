# Roam

Roam is an open-source, AGPL-licensed short-form video social network in which you can swipe through geolocated videos from anywhere in the world.

## Installation & Usage

```bash
git clone https://github.com/VeryUsual/roam
python -m venv .venv
source .venv/bin/activate # Use "venv\Scripts\activate.bat" for Microsoft Windows
pip install -r requirements.txt
flask run
```


## Code formatting & testing
- All Python code must be formatted by black ([https://github.com/psf/black](https://github.com/psf/black))
- Run `python3 tests.py`, all unit tests must pass.


## License

This program is free software: you can redistribute it and/or modify

it under the terms of the GNU Affero General Public License as published by

the Free Software Foundation, either version 3 of the License, or

(at your option) any later version.

This program is distributed in the hope that it will be useful,

but WITHOUT ANY WARRANTY; without even the implied warranty of

MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the

GNU Affero General Public License for more details.

See (www.gnu.org/licenses)[https://www.gnu.org/licenses/] or the LICENSE file contained in this program for the full GNU Affero General Public License.