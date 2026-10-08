# Third-party notices for the ECHO extension layer

This file records installed direct Python dependencies used by ECHO and the
optional InflationForge service adapter. The notices below are copied from
local distribution license files and the bundled InflationForge `LICENSE`.
They preserve upstream attribution; the ECHO core, manifests, and independently
written adapters are first-party work whose repository-wide license is
`NOASSERTION` in this inventory.

The [SBOM](docs/extensions/sbom.json) lists the actual inspected ECHO Python
environment, including indirect dependencies and development tooling, with raw
license metadata and hashes/paths for installed license files. Retain those
files when distributing the corresponding packages. This document is not a
complete monorepo, container, operating-system, dataset, or model license audit.
No vulnerability scan or upstream revision match is implied by the inventory.

The MIT FalkorDB **Python client** notice below does not establish the license
of the separately operated FalkorDB server container. The server image is pinned
in `compose.echo.yaml`; review that image and its notices independently before
redistribution or deployment. No server-image license is inferred here.

GreenChain, PROXY, and Rumi activation remains deferred as described in the
[extension intake dossier](docs/extensions/intake/bundled-projects.md). Keeping
a bundled folder is not evidence of an open-source redistribution grant. No
upstream code from those projects was copied into the ECHO extension adapters.
Their license uncertainty is retained in the project license review.

## Direct dependency metadata

| Package | Installed version | Local license evidence |
|---|---|---|
| FalkorDB | 1.6.0 | License :: OSI Approved :: MIT License |
| fastapi | 0.115.6 | License :: OSI Approved :: MIT License |
| pydantic | 2.10.4 | MIT |
| PyYAML | 6.0.2 | MIT |
| uvicorn | 0.32.1 | BSD-3-Clause |

## Preserved Python dependency license texts

### FalkorDB 1.6.0

Source: `.venv-echo/Lib/site-packages/falkordb-1.6.0.dist-info/licenses/LICENSE`.

```text
MIT License

Copyright (c) 2023 FalkorDB

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### fastapi 0.115.6

Source: `.venv-echo/Lib/site-packages/fastapi-0.115.6.dist-info/licenses/LICENSE`.

```text
The MIT License (MIT)

Copyright (c) 2018 Sebastián Ramírez

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

### pydantic 2.10.4

Source: `.venv-echo/Lib/site-packages/pydantic-2.10.4.dist-info/licenses/LICENSE`.

```text
The MIT License (MIT)

Copyright (c) 2017 to present Pydantic Services Inc. and individual contributors.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### PyYAML 6.0.2

Source: `.venv-echo/Lib/site-packages/PyYAML-6.0.2.dist-info/LICENSE`.

```text
Copyright (c) 2017-2021 Ingy döt Net
Copyright (c) 2006-2016 Kirill Simonov

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### uvicorn 0.32.1

Source: `.venv-echo/Lib/site-packages/uvicorn-0.32.1.dist-info/licenses/LICENSE.md`.

```text
Copyright © 2017-present, [Encode OSS Ltd](https://www.encode.io/).
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Optional InflationForge bundled service

The independently written adapter calls an existing, separately operated
read-only interface. No upstream source was copied into the adapter.
`Inflation-Forge-main/LICENSE` contains the MIT text and copyright below.
The inspected PeoplePay folder tree is `e563d5acf09f89a76fbc65aa9451fc0d3cf10762`. This is a local tree
identity; the matching upstream commit is not established.

```text
MIT License

Copyright (c) 2026 Kaushik Sivakumar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Updating this record

After changing the ECHO requirements or installed environment, regenerate the
installed package inventory from `.venv-echo` metadata and inspect its license
files. Record newly accepted upstream commits and retain their original
copyright/NOTICE files. Do not replace missing license evidence with a guessed
SPDX identifier. Keep server, data, model, and application license reviews
separate from Python package metadata.


## CivicMesh

CivicMesh is bundled under MIT, copyright (c) 2026 Anbu. Original notice/license: `CivicMesh-main/LICENSE`. Declared upstream: https://github.com/Anbu-00001/CivicMesh. Native project version 1.0.0; upstream commit was not supplied and is unknown. Original algorithms, policy data, UI and test suites are upstream work. PeoplePay adds an adapter, normalized evidence/decision intake, workflow routing and portal. See `docs/integration/CIVICMESH_UPSTREAM.md`.

## World Bank Open Data (HYPERGRID fixture)

`packages/peoplepay-hypergrid/fixtures/worldbank_snapshot.json` contains annual observations retrieved from the World Bank Open Data API v2
(indicators FP.CPI.TOTL for India and the United States, and PA.NUS.FCRF for India) on 2026-10-08. World Bank Open Data is published under CC BY 4.0;
attribution to The World Bank is required on redistribution. The file records the source URL, retrieval time, `lastupdated` value and a SHA-256 of each
API response. The series are annual and the provider exposes no revision history, so the data is labelled HISTORICAL and not vintage-aware.
