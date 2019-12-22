# torrent_info_sjva

libtorrent를 이용해 마그넷이나 토렌트 파일의 정보를 보여주는 SJVA 플러그인

## 요구조건

libtorrent가 설치가능한 모든 환경.

자동 설치는 아래 환경만 지원합니다.
- x86_64
- alpine 3.10
- docker

네이티브라면 직접 설치 후 설정 페이지에서 설치 여부를 확인할 수 있습니다.

## 준비과정

## 더 읽어보기

## Changelog

v0.0.0.5
- WEBUI: 결과를 json 대신 좀 더 보기 좋은 포맷으로
- WEBUI: 항목 클릭해서 복사
- WEBUI: magnet:?xt=urn:btih:로 시작안하는 마그넷은 인포해쉬로 간주

v0.0.0.4
- LOGIC: 자체 캐시를 좀 더 적극적으로 활용, 웹에서 검색시 등...

## TODO

- FRAMEWORK: flask_restful Resource를 쓸 수 있으면 좀 더 좋지 않을까?
- LOGIC: api 정리. flask_restful 이용
- LOGIC: 사용자 트래커 기능
- LOGIC: 시간에 관계된 데이터 로컬 시간으로?
- LOGIC: --no-cache 옵션
- WEBUI: cosmetic issue, button align, responsive view
